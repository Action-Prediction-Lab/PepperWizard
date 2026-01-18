from PIL import Image, ImageDraw, ImageFont

ascii_art = r"""
__________                                   __      __.__                         .__
\______   \ ____ ______ ______   ___________/  \    /  \__|____________ _______  __| /
 |     ___// __  \____  \____ \_/ __ \_  __ \   \/\   /  \___   /\__  \_  __ \/ __  | 
 |    |   \  ___/|  |_> >  |_> >  ___/|  | \/        /|  |/    /  / __ \|  | \/ /_/ | 
 |____|    \___  >   __/|   __/ \___  >__|    \_/\  / |__/_____ \(____  /__|  \____ | 
                 |__|   |__|                      \/           \/     \/           \/ 
--------------------------------------------------------------------------------------
"""
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
font_size = 20

themes = {
    "original":   {"bg": (15, 23, 42),  "text": (56, 189, 248)},	# Slate/Blue
    "blade":      {"bg": (1, 22, 30),   "text": (255, 155, 50)},	# Teal/Orange
    "matrix":     {"bg": (0, 20, 0),    "text": (0, 255, 70)},  	# Black/Green
    "cyberpunk":  {"bg": (45, 0, 60),   "text": (0, 255, 242)},		# Purple/Cyan
    "monochrome": {"bg": (10, 10, 10),  "text": (240, 240, 240)},	# Black/White
    "terminal":   {"bg": (0, 0, 0),     "text": (50, 205, 50)},		# Retro Terminal
    "solarized":  {"bg": (0, 43, 54),   "text": (131, 148, 150)},	# Solarized Dark
    "dracula":    {"bg": (40, 42, 54),  "text": (255, 121, 198)} 	# Grey/Pink
}

temp_img = Image.new("RGB", (1, 1))
temp_draw = ImageDraw.Draw(temp_img)
try:
    font = ImageFont.truetype(font_path, font_size)
except IOError:
    font = ImageFont.load_default()

bbox = temp_draw.textbbox((0, 0), ascii_art, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]

padding = 60
final_w = text_width + (padding * 2)
final_h = text_height + (padding * 2)

for name, colors in themes.items():
    image = Image.new("RGB", (final_w, final_h), colors["bg"])
    draw = ImageDraw.Draw(image)

    x = (final_w - text_width) / 2
    y = (final_h - text_height) / 2

    draw.text((x, y), ascii_art, fill=colors["text"], font=font)
    
    filename = f"assets/banner_{name}.png"
    image.save(filename)
    print(f"Generated {filename}")
