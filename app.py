from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from wtforms import StringField, PasswordField, TextAreaField
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import os

app = Flask(__name__, template_folder=os.path.abspath("templates"))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
app.config['SECRET_KEY'] = '12345'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    avatar = db.Column(db.String(255))
    description = db.Column(db.Text)
    is_admin = db.Column(db.Boolean, default=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)


class RegisterForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    description = TextAreaField('Описание')


class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])


class PostForm(FlaskForm):
    title = StringField('Заголовок', validators=[DataRequired()])
    content = TextAreaField('Текст поста', validators=[DataRequired()])


class CommentForm(FlaskForm):
    content = TextAreaField('Комментарий', validators=[DataRequired()])


class EditProfileForm(FlaskForm):
    description = TextAreaField('Описание')
    avatar = FileField('Аватар (изображение)', validators=[
        FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Только изображения!')
    ])


class MakeAdminForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    sort_by = request.args.get('sort', 'new')
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)

    # Начальный запрос
    posts_query = Post.query
    if search_query:
        posts_query = posts_query.filter(Post.title.ilike(f'%{search_query}%'))

    # Сортировка
    if sort_by == 'popular':
        posts_query = db.session.query(Post).outerjoin(Comment).group_by(Post.id).order_by(db.func.count(Comment.id).desc())
        if search_query:
            posts_query = posts_query.filter(Post.title.ilike(f'%{search_query}%'))

    else:
        posts_query = posts_query.order_by(Post.date.desc())

    # Пагинация
    pagination = posts_query.paginate(page=page, per_page=5)
    posts = pagination.items

    return render_template('index.html', posts=posts, sort_by=sort_by, pagination=pagination, search_query=search_query)


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            password=form.password.data,
            avatar='https://via.placeholder.com/60 ',
            description=form.description.data
        )
        db.session.add(user)
        db.session.commit()
        flash("Вы успешно зарегистрировались!")
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.password == form.password.data:
            login_user(user)
            flash("Вы вошли в систему")
            return redirect(url_for('index'))
        flash("Неверный логин или пароль")
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы")
    return redirect(url_for('index'))


@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, user_id=current_user.id)
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit_post.html', form=form, title="Создать пост")


@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)

    # Разрешаем редактировать автору ИЛИ админу
    if post.author.id != current_user.id and not current_user.is_admin:
        flash("У вас нет прав на редактирование этого поста.")
        return redirect(url_for('view_post', post_id=post_id))

    form = PostForm(obj=post)
    if form.validate_on_submit():
        form.populate_obj(post)
        db.session.commit()
        flash("Пост обновлён!")
        return redirect(url_for('view_post', post_id=post_id))
    return render_template('edit_post.html', form=form, title="Редактировать пост", post=post)


@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    # Проверка прав
    if post.author.id != current_user.id and not current_user.is_admin:
        flash("У вас нет прав на удаление этого поста.")
        return redirect(url_for('index'))

    db.session.delete(post)
    db.session.commit()
    flash("Пост удален")
    return redirect(url_for('index'))


@app.route('/delete_comment/<int:comment_id>/<int:post_id>')
@login_required
def delete_comment(comment_id, post_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.author.id != current_user.id:
        flash("Вы не можете удалить чужой комментарий.")
        return redirect(url_for('view_post', post_id=post_id))
    db.session.delete(comment)
    db.session.commit()
    flash("Комментарий удален")
    return redirect(url_for('view_post', post_id=post_id))


@app.route('/profile/<int:user_id>')
def profile(user_id):
    user = User.query.get_or_404(user_id)
    posts = Post.query.filter_by(user_id=user_id).order_by(Post.date.desc()).all()
    return render_template('profile.html', user=user, posts=posts)


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(obj=current_user)

    if form.validate_on_submit():
        # Получаем загруженный файл
        avatar = form.avatar.data

        # Обновляем описание
        current_user.description = form.description.data

        # Если выбран новый аватар
        if avatar and allowed_file(avatar.filename):
            filename = secure_filename(f"{current_user.id}_{avatar.filename}")
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.avatar = f'uploads/{filename}'

        db.session.commit()
        flash("Профиль успешно обновлён!")
        return redirect(url_for('profile', user_id=current_user.id))

    return render_template('edit_profile.html', form=form, user=current_user)


@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(content=form.content.data, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
        return redirect(url_for('view_post', post_id=post_id))

    comments = Comment.query.filter_by(post_id=post_id).order_by(Comment.date.asc()).all()
    return render_template('post.html', post=post, comments=comments, form=form)


@app.route('/admin/make_admin', methods=['GET', 'POST'])
@login_required
def make_admin():
    if not current_user.is_admin:
        abort(403)

    form = MakeAdminForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            user.is_admin = True
            db.session.commit()
            flash(f"Пользователь {user.username} назначен администратором")
        else:
            flash("Пользователь не найден")
        return redirect(url_for('make_admin'))

    return render_template('make_admin.html', form=form)


@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if not current_user.is_admin:
        abort(403)

    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)

    # Поиск пользователей
    users_query = User.query
    if search_query:
        users_query = users_query.filter(User.username.ilike(f'%{search_query}%'))

    pagination = users_query.paginate(page=page, per_page=10)
    users = pagination.items

    # Обработка изменения прав администратора
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        is_admin_value = request.form.get(f'is_admin_{user_id}') == 'on'

        user = User.query.get_or_404(user_id)

        # Нельзя снять права с себя
        if user.id == current_user.id and not is_admin_value:
            flash("Вы не можете лишить себя прав администратора")
        else:
            user.is_admin = is_admin_value
            db.session.commit()
            flash(f"Права пользователя {user.username} обновлены")

        return redirect(url_for('admin_users', search=search_query))

    return render_template('admin_users.html', users=users, pagination=pagination, search_query=search_query)


@app.route('/debug-admins')
def debug_admins():
    admins = User.query.filter_by(is_admin=True).all()
    return '<br>'.join([f'{u.username} (ID: {u.id})' for u in admins])


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
