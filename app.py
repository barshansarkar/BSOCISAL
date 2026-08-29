from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
from datetime import datetime

from config import Config
from models import db, User, Post, PostImage, Like, Comment, Bookmark, Follow, Notification
from forms import LoginForm, RegistrationForm, PostForm, CommentForm, ProfileForm
from utils import save_picture, delete_picture, validate_image_count
from flask import session
app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create tables
with app.app_context():
    db.create_all()


@app.route('/')
def index():
    # Get feed type from query parameter
    feed_type = request.args.get('feed', 'all')
    
    if feed_type == 'following' and current_user.is_authenticated:
        # Show only posts from users the current user follows
        followed_users = [follow.followed_id for follow in current_user.following.all()]
        if followed_users:
            posts = Post.query.filter(Post.user_id.in_(followed_users)).order_by(Post.created_at.desc()).all()
        else:
            posts = []
    else:
        # Show all posts
        posts = Post.query.order_by(Post.created_at.desc()).all()

    # Build suggested users with follow status
    suggested_users = []
    if current_user.is_authenticated:
        # Owner first
        suggested_users.append({
            'user': current_user,
            'is_following': False  # yourself
        })
        # Random other users
        random_users = User.query.filter(User.id != current_user.id).order_by(db.func.random()).limit(15).all()
        for user in random_users:
            suggested_users.append({
                'user': user,
                'is_following': current_user.is_following(user)
            })
    else:
        random_users = User.query.order_by(db.func.random()).limit(15).all()
        suggested_users = [{'user': u, 'is_following': False} for u in random_users]

    return render_template('index.html', posts=posts, suggested_users=suggested_users, feed_type=feed_type)


@app.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow_user(user_id):
    user_to_follow = User.query.get_or_404(user_id)
    if user_to_follow == current_user:
        return jsonify({'error': 'Cannot follow yourself'}), 400

    if current_user.is_following(user_to_follow):
        # Unfollow
        follow = current_user.following.filter_by(followed_id=user_id).first()
        if follow:
            db.session.delete(follow)
            db.session.commit()
            return jsonify({'following': False, 'follower_count': user_to_follow.follower_count()})
    else:
        # Follow - create notification
        follow = Follow(follower_id=current_user.id, followed_id=user_to_follow.id)
        db.session.add(follow)
        db.session.flush()
        
        # Create notification for the followed user
        notification = Notification(
            user_id=user_to_follow.id,
            actor_id=current_user.id,
            type='follow',
            message=f'{current_user.username} started following you'
        )
        db.session.add(notification)
        db.session.commit()
        return jsonify({'following': True, 'follower_count': user_to_follow.follower_count()})

    return jsonify({'error': 'Invalid request'}), 400


@app.route('/notifications')
@login_required
def notifications():
    # Get all notifications for the current user, ordered by newest first
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    # Mark all as read
    for notification in notifications:
        notification.read = True
    db.session.commit()
    return render_template('notifications.html', notifications=notifications)


@app.route('/notifications/unread_count')
@login_required
def unread_count():
    count = current_user.unread_count()
    return jsonify({'count': count})


@app.route('/followers/<username>')
def followers(username):
    user = User.query.filter_by(username=username).first_or_404()
    followers = user.followers.all()
    return render_template('followers.html', user=user, followers=followers)


@app.route('/following/<username>')
def following(username):
    user = User.query.filter_by(username=username).first_or_404()
    following = user.following.all()
    return render_template('following.html', user=user, following=following)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash('Logged in successfully!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html', form=form)


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    posts = []
    users = []
    if query:
        # Search posts by content
        posts = Post.query.filter(Post.content.ilike(f'%{query}%')).order_by(Post.created_at.desc()).limit(20).all()
        # Search users by username
        users = User.query.filter(User.username.ilike(f'%{query}%')).limit(20).all()
    return render_template('search.html', query=query, posts=posts, users=users)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form=form)


@app.route('/logout')
@login_required
def logout():
    session.pop('data_verified', None)   # clear the PIN flag
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(content=form.content.data, user_id=current_user.id)
        db.session.add(post)
        db.session.flush()

        if form.images.data:
            files = request.files.getlist('images')
            valid, message = validate_image_count(files)
            if not valid:
                flash(message, 'error')
                db.session.rollback()
                return render_template('create_post.html', form=form)

            for idx, file in enumerate(files):
                if file and file.filename:
                    filename = save_picture(file, 'uploads')
                    post_image = PostImage(filename=filename, order=idx, post_id=post.id)
                    db.session.add(post_image)

        db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('index'))

    return render_template('create_post.html', form=form)


@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    form = CommentForm()

    if form.validate_on_submit() and current_user.is_authenticated:
        comment = Comment(content=form.content.data, user_id=current_user.id, post_id=post.id)
        db.session.add(comment)
        db.session.flush()
        
        # Create notification for post owner
        if post.user_id != current_user.id:
            notification = Notification(
                user_id=post.user_id,
                actor_id=current_user.id,
                type='comment',
                post_id=post.id,
                message=f'{current_user.username} commented on your post: "{comment.content[:50]}..."'
            )
            db.session.add(notification)
        
        db.session.commit()
        flash('Comment added!', 'success')
        return redirect(url_for('view_post', post_id=post.id))

    return render_template('view_post.html', post=post, form=form)


@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    like = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first()

    if like:
        db.session.delete(like)
        liked = False
    else:
        like = Like(user_id=current_user.id, post_id=post.id)
        db.session.add(like)
        db.session.flush()
        
        # Create notification for post owner
        if post.user_id != current_user.id:
            notification = Notification(
                user_id=post.user_id,
                actor_id=current_user.id,
                type='like',
                post_id=post.id,
                message=f'{current_user.username} liked your post'
            )
            db.session.add(notification)
        
        liked = True

    db.session.commit()
    return jsonify({'liked': liked, 'count': post.like_count()})


@app.route('/post/<int:post_id>/bookmark', methods=['POST'])
@login_required
def bookmark_post(post_id):
    post = Post.query.get_or_404(post_id)
    bookmark = Bookmark.query.filter_by(user_id=current_user.id, post_id=post.id).first()

    if bookmark:
        db.session.delete(bookmark)
        bookmarked = False
    else:
        bookmark = Bookmark(user_id=current_user.id, post_id=post.id)
        db.session.add(bookmark)
        bookmarked = True

    db.session.commit()
    return jsonify({'bookmarked': bookmarked})


@app.route('/bookmarks')
@login_required
def bookmarks():
    bookmarks = Bookmark.query.filter_by(user_id=current_user.id).order_by(Bookmark.created_at.desc()).all()
    posts = [bookmark.post for bookmark in bookmarks]
    return render_template('bookmarks.html', posts=posts)


@app.route('/profile/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template('profile.html', user=user, posts=posts)


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = ProfileForm()
    if form.validate_on_submit():
        if form.bio.data is not None:
            current_user.bio = form.bio.data

        if form.avatar.data and form.avatar.data.filename:
            if current_user.avatar != 'default_avatar.png':
                delete_picture(current_user.avatar, 'profile_pics')

            filename = save_picture(form.avatar.data, 'profile_pics', (150, 150))
            current_user.avatar = filename

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile', username=current_user.username))

    elif request.method == 'GET':
        form.bio.data = current_user.bio

    return render_template('edit_profile.html', form=form)


@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        flash('You cannot delete this post.', 'error')
        return redirect(url_for('index'))

    for image in post.images:
        delete_picture(image.filename, 'uploads')

    db.session.delete(post)
    db.session.commit()
    flash('Post deleted!', 'success')
    return redirect(url_for('index'))

@app.route('/mydata', methods=['GET', 'POST'])
@login_required
def view_my_data():
    # Only admin
    if current_user.id != 1:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    # Already verified?
    if session.get('data_verified'):
        users = User.query.all()
        posts = Post.query.order_by(Post.created_at.desc()).all()
        images = PostImage.query.all()
        likes = Like.query.all()
        comments = Comment.query.all()
        bookmarks = Bookmark.query.all()
        stats = {
            'users': User.query.count(),
            'posts': Post.query.count(),
            'images': PostImage.query.count(),
            'likes': Like.query.count(),
            'comments': Comment.query.count(),
            'bookmarks': Bookmark.query.count()
        }
        return render_template('my_data.html', users=users, posts=posts,
                               images=images, likes=likes, comments=comments,
                               bookmarks=bookmarks, stats=stats)

    # Handle PIN form
    if request.method == 'POST':
        pin = request.form.get('pin')
        if pin == app.config.get('DATA_ACCESS_PIN', '1234'):
            session['data_verified'] = True
            flash('Access granted.', 'success')
            return redirect(url_for('view_my_data'))
        else:
            flash('Incorrect PIN.', 'error')

    # Show PIN form
    return render_template('data_login.html')

if __name__ == '__main__':
    app.run(debug=True)