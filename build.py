"""
Build the web interface: download all the external static files in the `static/ext/` directory
and save the remote repository URL.
"""

import subprocess as sp
from pathlib import Path
from posixpath import basename
from urllib.request import urlopen

try:
    import minify_html
except ImportError:
    minify_html = None

# Create the output folder
base_path = Path("static/ext")
base_path.mkdir(parents=True, exist_ok=True)

urls = [
    "https://cdn.jsdelivr.net/npm/@lowlighter/matcha@3.0.0/dist/matcha.css",
]
# Save files with better filenames
mappings = {
    "matcha": "matcha.min.css",
}

for url in urls:
    print(f"Downloading {url} ... ", end="")

    # Get the good filename: if any of the mapped terms is present,
    # replace the entire filename
    name = basename(url)
    for item, repl in mappings.items():
        if item in url:
            name = repl
            break

    # Save and minify the file
    output = base_path / name
    with urlopen(url) as rf, output.open("w") as f:
        data = rf.read().decode("utf-8")
        # Use a prefix to make minify-html think it's CSS or JavaScript
        prefix = {".html": "", ".css": "<style>", ".js": "<script>"}.get(output.suffix)
        if prefix is not None and minify_html:
            try:
                data = minify_html.minify(
                    prefix + data,
                    minify_css=True,
                    minify_js=True,
                    do_not_minify_doctype=True,
                ).removeprefix(prefix)
            except:  # pylint: disable=W0702
                pass
        f.write(data)

    print("OK")

# Save the remote repository URL
print("Saving the remote repository URL... ", end="")
try:
    url = (
        sp.check_output(["git", "remote", "get-url", "origin"], stderr=sp.STDOUT, text=True)
        .rstrip("\n")
        .removesuffix(".git")
    )
    (Path(__file__).parent / ".remote_url").write_text(url, "utf-8")
    print("OK")
except sp.CalledProcessError as err:
    print(f"Failed with return code {err.returncode}:\n{err.stdout}")
