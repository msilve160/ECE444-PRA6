import json
import os
from pathlib import Path

import pytest

TEST_DB = "test.db"
BASE_DIR = Path(__file__).resolve().parent.parent

# Flask-SQLAlchemy binds the database when the app is created, so point it at
# the test database BEFORE importing the app (keeps real data untouched).
os.environ["DATABASE_URL"] = f"sqlite:///{BASE_DIR.joinpath(TEST_DB)}"

from project.app import app, db  # noqa: E402


@pytest.fixture
def client():
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()  # setup
        yield app.test_client()  # tests run here
        db.drop_all()  # teardown


def login(client, username, password):
    """Login helper function"""
    return client.post(
        "/login",
        data=dict(username=username, password=password),
        follow_redirects=True,
    )


def logout(client):
    """Logout helper function"""
    return client.get("/logout", follow_redirects=True)


def add_post(client, title, text):
    """Helper: add a post (requires login first)"""
    return client.post("/add", data=dict(title=title, text=text), follow_redirects=True)


def test_index(client):
    response = client.get("/", content_type="html/text")
    assert response.status_code == 200


def test_database(client):
    """initial test. ensure that the database exists"""
    assert BASE_DIR.joinpath(TEST_DB).is_file()


def test_empty_db(client):
    """Ensure database is blank"""
    rv = client.get("/")
    assert b"No entries yet. Add some!" in rv.data


def test_login_logout(client):
    """Test login and logout using helper functions"""
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"])
    assert b"You were logged in" in rv.data
    rv = logout(client)
    assert b"You were logged out" in rv.data
    rv = login(client, app.config["USERNAME"] + "x", app.config["PASSWORD"])
    assert b"Invalid username" in rv.data
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"] + "x")
    assert b"Invalid password" in rv.data


def test_messages(client):
    """Ensure that user can post messages"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = add_post(client, "<Hello>", "<strong>HTML</strong> allowed here")
    assert b"No entries here so far" not in rv.data
    assert b"&lt;Hello&gt;" in rv.data
    assert b"<strong>HTML</strong> allowed here" in rv.data


def test_add_requires_login(client):
    """Posting while logged out is rejected with 401"""
    rv = client.post("/add", data=dict(title="a", text="b"))
    assert rv.status_code == 401


def test_delete_message(client):
    """Ensure the messages are being deleted (login required)"""
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 0
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 1


def test_delete_requires_login_returns_401(client):
    """Logged-out delete returns 401 and does not remove the post"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    add_post(client, "Keep me", "still here")
    logout(client)
    rv = client.get("/delete/1")
    assert rv.status_code == 401
    assert json.loads(rv.data)["message"] == "Please log in."
    rv = client.get("/")
    assert b"Keep me" in rv.data


def test_delete_removes_post(client):
    """Logged-in delete actually removes the post from the page"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    add_post(client, "Delete me", "bye")
    rv = client.get("/delete/1")
    assert rv.status_code == 200
    rv = client.get("/")
    assert b"Delete me" not in rv.data
    assert b"No entries yet. Add some!" in rv.data


def test_search_page_loads(client):
    """Search page renders with no query"""
    rv = client.get("/search/")
    assert rv.status_code == 200
    assert b"Search:" in rv.data


def test_search_finds_matching_post(client):
    """Search matches title or text, case-insensitively"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    add_post(client, "Python tips", "use pytest")
    add_post(client, "Cooking", "boil water")
    rv = client.get("/search/?query=PYTHON")
    assert b"Python tips" in rv.data
    assert b"Cooking" not in rv.data
    rv = client.get("/search/?query=water")
    assert b"Cooking" in rv.data
    assert b"Python tips" not in rv.data


def test_search_no_match(client):
    """A query with no matches shows no posts"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    add_post(client, "Hello", "world")
    rv = client.get("/search/?query=zzzz")
    assert rv.status_code == 200
    assert b"Hello" not in rv.data
