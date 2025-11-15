# Imports
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from dotenv import load_dotenv
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import pytz
import re

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.urandom(24)


def extract_first_image(html):
    match = re.search(r'<img[^>]+src="([^"]+)"', html)
    return match.group(1) if match else ''

def strip_html(html):
    return re.sub(r'<[^>]*>', '', html)


UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB file limit

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Register the custom Jinja2 filter for URL encoding
@app.template_filter('url_encode')
def url_encode_filter(value):
    return quote(value)

# Register helper functions as Jinja2 filters
@app.template_filter('extract_first_image')
def extract_first_image_filter(html):
    return extract_first_image(html)

@app.template_filter('strip_html')
def strip_html_filter(html):
    return strip_html(html)

# Database path
DATABASE = os.path.join(app.instance_path,'blog.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Login credentials and session secret key
USERNAME = "admin"
PASSWORD = "secret"
app.secret_key = "supersecretkeychangeitlater"


# Create the database and posts table if it doesn't exist
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def add_slug_column():
    try:
        with sqlite3.connect(DATABASE) as conn:
            # Check if column exists
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(posts)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'slug' not in columns:
                conn.execute("ALTER TABLE posts ADD COLUMN slug TEXT")
                print("Added 'slug' column to posts table")
                
                # Generate slugs for existing posts
                cursor.execute("SELECT id, title FROM posts WHERE slug IS NULL OR slug = ''")
                posts = cursor.fetchall()
                
                for post_id, title in posts:
                    # Create a simple slug from title
                    slug = title.lower().replace(' ', '-')
                    # Remove special characters
                    slug = ''.join(c for c in slug if c.isalnum() or c == '-')
                    # Add timestamp to ensure uniqueness
                    import time
                    slug = f"{slug}-{int(time.time())}"
                    
                    conn.execute("UPDATE posts SET slug = ? WHERE id = ?", (slug, post_id))
                
                conn.commit()
                print(f"Generated slugs for {len(posts)} existing posts")
            else:
                print("'slug' column already exists")
    except Exception as e:
        print(f"Error adding slug column: {e}")


    # App Routes
@app.route("/")
def home():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute("SELECT id, title, content, tags, created_at FROM posts ORDER BY created_at DESC")
        raw_posts = cursor.fetchall()

    # Generate previews with Markdown formatting
    posts = []
    for post in raw_posts:
        full_content = post[2]
        preview_text = full_content[:300]
       
        posts.append((post[0], post[1], preview_text, post[3], post[4], len(full_content) > 300))

    return render_template("home.html")

@app.route("/blog")
def blog():
    page = int(request.args.get("page", 1))
    per_page = 5
    offset = (page - 1) * per_page

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        total_pages = (total_posts + per_page - 1) // per_page

        posts = conn.execute(
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()

        for i, post in enumerate(posts):
            post_dict = dict(post)
            post_dict['first_image'] = extract_first_image(post_dict['content'])
            post_dict['excerpt'] = strip_html(post_dict['content'])[:200]
            posts[i] = post_dict

    return render_template("blog.html", posts=posts, page=page, total_pages=total_pages)


@app.route('/new', methods=['GET', 'POST'])
def new_post():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title'].strip()
        content = request.form['content'].strip()
        tags = request.form.get('tags', '').strip()
        status = request.form.get('status', 'draft').strip()
        format = request.form.get('format', 'standard').strip()
        slug = request.form.get('slug', '').strip().lower().replace(' ', '-')

        # Validate slug
        if not slug or not re.match(r'^[a-z0-9\-]+$', slug):
            flash("Slug can only contain lowercase letters, numbers, and hyphens.", "danger")
            return redirect(url_for('new_post'))

        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with sqlite3.connect(DATABASE) as conn:
            conn.execute(
                "INSERT INTO posts (title, content, tags, status, format, slug, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title, content, tags, status, format, slug, created_at)
            )
            conn.commit()

        flash("Post created successfully!", "success")
        return redirect(url_for('dashboard'))

    return render_template('new_post.html')




@app.route('/edit/<slug>', methods=["GET", "POST"])
def edit(slug):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row  # This makes results accessible as dictionaries
        cursor = conn.execute("SELECT * FROM posts WHERE slug = ?", (slug,))
        post = cursor.fetchone()
        if post is None:
            return "Post not found", 404

    error = None
    if request.method == "POST":
        status = request.form.get("status", "draft")
        format = request.form.get("format", "html")
        status = request.form.get("status", "draft")
        format = request.form.get("format", "html")
        title = request.form.get("title")
        content = request.form.get("content")
        tags = request.form.get("tags", "")

        with sqlite3.connect(DATABASE) as conn:
            conn.execute("UPDATE posts SET title = ?, content = ?, tags = ?, status = ?, format = ? WHERE slug = ?",
                         (title, content, tags, status, format, slug))
            conn.commit()
        return redirect(url_for("dashboard"))

    return render_template("edit_post.html", post=post, error=error)


@app.route("/delete/<slug>", methods=["POST"])  # Changed from post_id to slug
def delete(slug):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("DELETE FROM posts WHERE slug = ?", (slug,))
        conn.commit()
    return redirect(url_for("dashboard"))
   

@app.template_filter('format_datetime')
def format_datetime(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        dt = dt.astimezone(pytz.timezone('US/Central'))
        return dt.strftime("%m/%d/%y %I:%M %p CST")
    except Exception:
        return value


@app.route("/tag/<tag_name>")
def posts_by_tag(tag_name):
    page = request.args.get('page', 1, type=int)
    posts_per_page = 5
    offset = (page - 1) * posts_per_page

    # Get the posts for the specific tag
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row  # This makes rows behave like dictionaries
        cursor = conn.execute(
            "SELECT id, title, slug, content, tags, created_at FROM posts WHERE tags LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (f"%{tag_name}%", posts_per_page, offset)
        )
        posts = cursor.fetchall()

        cursor = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE tags LIKE ?",
            (f"%{tag_name}%",)
        )
        total_posts = cursor.fetchone()[0]

    # Group posts by year
    grouped_posts = {}
    for post in posts:
        year = post['created_at'][:4]  # Extract year from 'created_at'
        if year not in grouped_posts:
            grouped_posts[year] = []
        grouped_posts[year].append(post)

    total_pages = (total_posts + posts_per_page - 1) // posts_per_page
    return render_template("tag_posts.html", posts=grouped_posts, tag=tag_name, page=page, total_pages=total_pages)



@app.route('/archives')
def archives():
    page = int(request.args.get('page', 1))  # Default to page 1 if no page is specified
    per_page = 5  # Number of posts per page
    offset = (page - 1) * per_page  # Calculate offset for pagination

    with sqlite3.connect(DATABASE) as conn:
        # Get the total number of posts
        total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        total_pages = (total_posts + per_page - 1) // per_page  # Total number of pages

        # Fetch posts for the current page
        posts = conn.execute(
            "SELECT id, title, content, slug, tags, created_at FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()

        # Group posts by year for the archives sidebar
        archives = {}
        for post in posts:
            year = post[5][:4]  # Extract year from created_at (post[5])
            print(f"Year: {year}")  # Debugging print to see what year values are returned
            if year not in archives:
                archives[year] = []
            archives[year].append({
                'slug': post[3],
                'title': post[1],
                'created_at': post[5],
            })

    return render_template('archives.html', archives=archives, page=page, total_pages=total_pages)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        status = request.form.get("status", "draft")
        format = request.form.get("format", "html")
        status = request.form.get("status", "draft")
        format = request.form.get("format", "html")
        if request.form["username"] == USERNAME and request.form["password"] == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    page = int(request.args.get("page", 1))
    per_page = 5
    offset = (page - 1) * per_page

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        total_pages = max(1, (total + per_page - 1) // per_page)

        # Redirect if page number is out of bounds
        if page > total_pages:
            return redirect(url_for('dashboard', page=total_pages))
        elif page < 1:
            return redirect(url_for('dashboard', page=1))

        posts = conn.execute(
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()

    return render_template("dashboard.html", posts=posts, page=page, total_pages=total_pages)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        # For now, just print to the console
        print("Contact Form Submission:")
        print(f"Name: {name}")
        print(f"Email: {email}")
        print(f"Message: {message}")

        flash("Message sent successfully!")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html")

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return render_template("search_results.html", posts=[], query=query)

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        posts = conn.execute(
            "SELECT * FROM posts WHERE status = 'published' AND (title LIKE ? OR tags LIKE ?) ORDER BY created_at DESC",
            (f"%{query}%", f"%{query}%")
        ).fetchall()

        print(f"Search query: {query}")
        print(f"Posts found: {len(posts)}")
        for post in posts:
            print(f"- {post['title']}")
 
        # Optional: build excerpts for results
        for i, post in enumerate(posts):
            post_dict = dict(post)
            post_dict["excerpt"] = strip_html(post_dict["content"])[:200]
            post_dict["slug"] = post["slug"]
            post_dict["title"] = post["title"]
            posts[i] = post_dict

    return render_template("search_results.html", posts=posts, query=query)

@app.route('/post/<slug>')
def view_post(slug):
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        post = conn.execute("SELECT * FROM posts WHERE slug = ?", (slug,)).fetchone()

        if not post:
            return "Post not found", 404

        # Extract tags if present
        tag_list = [t.strip() for t in post['tags'].split(',')] if post['tags'] else []

        return render_template('view_post.html', post=post, tags=tag_list)


# Custom 404 error handler
@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404


@app.route('/upload', methods=['GET', 'POST'])
def upload_image():
    if request.method == 'POST':
        file = request.files.get('file')

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            file_url = url_for('static', filename=f'uploads/{filename}')
            return render_template("upload_success.html", file_url=file_url)

        return "Invalid file or unsupported format."

    return render_template("upload.html")


@app.route('/uploads')
def view_uploads():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    files = os.listdir(app.config['UPLOAD_FOLDER'])
    image_urls = [
        url_for('static', filename=f'uploads/{f}')
        for f in files if allowed_file(f)
    ]
    return render_template('uploads.html', images=image_urls)


@app.route('/delete-image/<filename>', methods=['POST'])
def delete_image(filename):
    if not session.get('logged_in'):
        flash("You must be logged in to delete images.", "danger")
        return redirect(url_for('login'))

    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        if os.path.exists(image_path):
            os.remove(image_path)
            flash("Image deleted successfully.", "success")
        else:
            flash("Image not found.", "warning")
    except Exception as e:
        flash(f"Error deleting image: {e}", "danger")

    return redirect(url_for('view_uploads'))
    
    
    
if __name__ == "__main__":
    with app.app_context():
        init_db()
        add_slug_column()
    app.run(debug=True)






