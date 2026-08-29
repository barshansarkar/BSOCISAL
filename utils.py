import os
import uuid
from PIL import Image
from flask import current_app
from config import Config

def save_picture(form_picture, folder='uploads', output_size=(800, 800)):
    """Save and compress uploaded image"""
    random_hex = uuid.uuid4().hex
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static', folder, picture_fn)
    
    # Compress and save image
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path, optimize=True, quality=85)
    
    return picture_fn

def delete_picture(filename, folder='uploads'):
    """Delete an image file"""
    if filename and filename != 'emptyprofile.jpg':
        picture_path = os.path.join(current_app.root_path, 'static', folder, filename)
        if os.path.exists(picture_path):
            os.remove(picture_path)

def get_image_url(filename, folder='uploads'):
    """Generate URL for an image"""
    return f'/static/{folder}/{filename}'

def validate_image_count(files):
    """Validate number of images uploaded"""
    image_count = len([f for f in files if f.filename])
    if image_count > Config.POST_IMAGES_MAX:
        return False, f'Maximum {Config.POST_IMAGES_MAX} images allowed'
    return True, ''