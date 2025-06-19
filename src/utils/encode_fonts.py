import base64
import os

def encode_font(font_path):
    """Convert a font file to base64 string"""
    with open(font_path, 'rb') as font_file:
        return base64.b64encode(font_file.read()).decode('utf-8')

def main():
    """Encode Cairo fonts and print their base64 representation"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    fonts_dir = os.path.join(project_root, 'assets', 'fonts')

    font_files = {
        'Cairo-Regular.ttf': os.path.join(fonts_dir, 'Cairo-Regular.ttf'),
        'Cairo-Bold.ttf': os.path.join(fonts_dir, 'Cairo-Bold.ttf')
    }

    print("# Copy these base64 strings to reports.py")
    print("\n# Cairo Regular")
    print("CAIRO_REGULAR_BASE64 = '''")
    print(encode_font(font_files['Cairo-Regular.ttf']))
    print("'''")
    
    print("\n# Cairo Bold")
    print("CAIRO_BOLD_BASE64 = '''")
    print(encode_font(font_files['Cairo-Bold.ttf']))
    print("'''")

if __name__ == '__main__':
    main()
