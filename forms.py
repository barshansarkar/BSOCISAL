from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, PasswordField, SubmitField, SelectField, HiddenField
from wtforms.validators import DataRequired, Email, Length, ValidationError
from models import User
from config import Config

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired()])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already taken.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered.')


class PostForm(FlaskForm):
    content = TextAreaField('Content', validators=[DataRequired(), Length(max=1000)])
    images = FileField('Images', validators=[FileAllowed(Config.ALLOWED_EXTENSIONS, 'Images only!')])
    submit = SubmitField('Post')


class CommentForm(FlaskForm):
    content = TextAreaField('Comment', validators=[DataRequired(), Length(max=500)])
    submit = SubmitField('Comment')


class ProfileForm(FlaskForm):
    bio = TextAreaField('Bio', validators=[Length(max=160)])
    avatar = FileField('Avatar', validators=[FileAllowed(Config.ALLOWED_EXTENSIONS, 'Images only!')])
    submit = SubmitField('Update Profile')


class ReportForm(FlaskForm):
    reason = SelectField('Reason', choices=[
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('inappropriate', 'Inappropriate content'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    details = TextAreaField('Details', validators=[Length(max=500)])
    submit = SubmitField('Submit Report')