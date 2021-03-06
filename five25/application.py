import os
import requests

from flask import flash, Flask, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from functools import wraps
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required

# Configure application
app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route('/')
@login_required
def index():
    """Show table of user's task lists."""

    user_id = session['user_id']
    lists = db.execute(
        'SELECT * FROM lists WHERE user_id = :user_id ORDER BY created DESC', {'user_id': user_id}
    ).fetchall()
    user = db.execute(
        'SELECT username FROM users WHERE id = :user_id', {'user_id': user_id}
    ).fetchone()

    return render_template('index.html', lists=lists, user=user)


@app.route('/tasks/<int:list_id>')
@login_required
def tasks(list_id):
    """Display a task list."""

    list = db.execute(
        'SELECT * FROM lists WHERE id = :list_id', {'list_id': list_id}
    ).fetchone()

    focus = db.execute(
        'SELECT name FROM tasks WHERE list_id = :list_id AND distraction = FALSE AND completed = FALSE', {'list_id': list_id}
    ).fetchall()

    distractions = db.execute(
        'SELECT name FROM tasks WHERE list_id = :list_id AND distraction = TRUE and completed = FALSE', {'list_id': list_id}
    ).fetchall()

    completed = db.execute(
        'SELECT name FROM tasks WHERE list_id = :list_id AND completed = TRUE', {'list_id': list_id}
    ).fetchall()

    return render_template('tasks.html', list=list, focus=focus, distractions=distractions, completed=completed)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Register user, adapted from the Flask Tutorial.

    https://flask.palletsprojects.com/en/1.1.x/tutorial/views/
    """

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirmation = request.form.get('confirmation')
        error = None

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'
        elif password != confirmation:
            error = 'Password and confirmation must match.'
        elif db.execute(
            'SELECT id FROM users WHERE username = :username', {'username': username}
        ).fetchone() is not None:
            error = 'User {} is already registered.'.format(username)

        if error is None:
            db.execute(
                'INSERT INTO users (username, password) VALUES (:username, :password)',
                {'username': username, 'password': generate_password_hash(password)}
            )
            db.commit()

            # Remember user
            user = db.execute(
                'SELECT * FROM users WHERE username = :username', {'username': username}
            ).fetchone()
            session['user_id'] = user['id']

            return redirect('/')

        flash(error)

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Log user in (adpated from the Flask Tutorial) and redirect to most recent task list.

    https://flask.palletsprojects.com/en/1.1.x/tutorial/views/
    """

    session.clear()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        error = None
        user = db.execute(
            'SELECT * FROM users WHERE username = :username', {'username': username}
        ).fetchone()

        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            list = db.execute(
                'SELECT * FROM lists WHERE user_id = :user_id ORDER BY created DESC', {'user_id': session['user_id']}
            ).fetchone()
            if list is None:
                return redirect('/')
            else:
                list_id = list.id
                return redirect(url_for('tasks', list_id=list.id))

        flash(error)

    return render_template('login.html')


@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a task list."""

    user_id = session['user_id']

    if request.method == 'POST':
        title = request.form.get('title')
        db.execute(
            'INSERT INTO lists (title, user_id) VALUES (:title, :user_id)', {'title': title, 'user_id': user_id}
        )
        # 'order by created desc' in case there are multiple lists with the same name, this provides the most recent
        list = db.execute(
            'SELECT * FROM lists WHERE title = :title AND user_id = :user_id ORDER BY created DESC', {'title': title, 'user_id': user_id}
        ).fetchone()
        list_id = list.id
        tasks = request.form.getlist('task')
        for task in tasks:
            db.execute(
                'INSERT INTO tasks (name, list_id) VALUES (:task, :list_id)', {'task': task, 'list_id': list_id}
            )
        db.commit()

        distractions = db.execute(
            'SELECT name FROM tasks WHERE list_id = :list_id', {'list_id': list_id}
        ).fetchall()

        flash('Your list has been created. Now choose the tasks to prioritize.')

        return redirect(url_for('tasks', list_id=list_id))

    return render_template('create.html')


@app.route('/focus/<int:list_id>', methods=['POST'])
@login_required
def focus(list_id):
    """Choose tasks to prioritize (or unprioritize)."""

    priorities = request.form.getlist('task')
    for priority in priorities:
        db.execute(
            'UPDATE tasks SET distraction = NOT distraction WHERE list_id = :list_id AND name = :priority', {'list_id': list_id, 'priority': priority}
        )
    db.commit()

    return redirect(url_for('tasks', list_id=list_id))


@app.route('/complete/<int:list_id>', methods=['POST'])
@login_required
def complete(list_id):
    """Mark task(s) completed."""

    completed = request.form.getlist('task')
    for complete in completed:
        db.execute(
            'UPDATE tasks SET completed = TRUE WHERE list_id = :list_id AND name = :complete', {'list_id': list_id, 'complete': complete}
        )
    db.commit()

    return redirect(url_for('tasks', list_id=list_id))


@app.route('/delete_task/<int:list_id>', methods=['POST'])
@login_required
def delete_task(list_id):
    """Delete checked task(s)."""

    deleted = request.form.getlist('task')
    for delete in deleted:
        db.execute(
            'DELETE FROM tasks WHERE list_id = :list_id AND name = :delete', {'list_id': list_id, 'delete': delete}
        )
    db.commit()

    return redirect(url_for('tasks', list_id=list_id))


@app.route('/delete_list/<int:list_id>', methods=['POST'])
@login_required
def delete_list(list_id):
    """Delete the list."""

    db.execute(
        'DELETE FROM tasks WHERE list_id = :list_id', {'list_id': list_id}
    )
    db.execute(
        'DELETE FROM lists WHERE id = :list_id', {'list_id': list_id}
    )
    db.commit()

    return redirect('/')


@app.route('/add/<int:list_id>', methods=['GET', 'POST'])
@login_required
def add(list_id):
    """Add a task to the list."""

    list = db.execute(
        'SELECT * FROM lists WHERE id = :list_id', {'list_id': list_id}
    ).fetchone()

    if request.method == 'POST':
        task = request.form.get('task')
        db.execute(
            'INSERT INTO tasks (name, list_id) VALUES (:task, :list_id)', {'task': task, 'list_id': list_id}
        )
        db.commit()

        return redirect(url_for('tasks', list_id=list_id))

    return render_template('add.html', list=list)


@app.route('/about')
def about():
    """Display about page."""

    return render_template('about.html')


@app.route('/logout')
def logout():
    """Log user out."""

    session.clear()
    return redirect('/')


# Deployment help from https://stackabuse.com/deploying-a-flask-application-to-heroku/
if __name__ == '__main__':
    # Threaded option to enable multiple instances for multiple user access support
    app.run(threaded=True, port=5000)
