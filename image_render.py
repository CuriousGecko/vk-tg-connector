import urllib.request
from io import BytesIO

from PIL import Image


def render(base_image_url):
    response = urllib.request.urlopen(base_image_url)
    img_data = response.read()
    base_image = Image.open(BytesIO(img_data))

    overlay = Image.open("images/play.png")

    x = (base_image.width - overlay.width) // 2
    y = (base_image.height - overlay.height) // 2

    new_image = base_image.copy()
    new_image.paste(overlay, (x, y), overlay)

    img_byte_array = BytesIO()
    new_image.save(img_byte_array, format='JPEG')
    img_byte_array = img_byte_array.getvalue()

    return img_byte_array
