import os
import subprocess as sp
import sys
import tempfile
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from shutil import which
from typing import Literal

from flask import Flask, Response, redirect, render_template, request, session
from werkzeug.local import LocalProxy

try:
    import minify_html
except ImportError:
    minify_html = None

# True = already installed
# None = not installed (but will be installed)
# string = location of FFmpeg
_ffmpeg_path: str | Literal[True] | None = True if which("ffmpeg") else None


def get_ffmpeg_path():
    """
    Return a path pointing to a FFmpeg executable,
    or `None` if FFmpeg is already present or can't be installed.
    """
    global _ffmpeg_path

    # If FFmpeg is not in PATH, download and install it
    if _ffmpeg_path is None:
        try:
            import ffmpeg_downloader.__main__ as ffdl
            from ffmpeg_downloader import _backend, _config, _path
        except ImportError:
            pass
        else:
            _backend.get_dir = tempfile.gettempdir
            _config.get_dir = tempfile.gettempdir
            _path.get_dir = tempfile.gettempdir

            argv = sys.argv[:]

            sys.argv[:] = ["ffdl", "install", "-y", "--no-simlinks"]
            ffdl.main("ffdl")

            sys.argv[:] = argv

            # Get the path from the ffmpeg-downloader Python API
            import ffmpeg_downloader

            _ffmpeg_path = ffmpeg_downloader.ffmpeg_path

    # If FFmpeg is already installed, return None
    if _ffmpeg_path is True:
        return None

    return _ffmpeg_path


from shazamio import Shazam  # pylint: disable=C0413

# Get the remote URL for the home page
remote_url_file = Path(__file__).parent / ".remote_url"
remote_url = remote_url_file.read_text("utf-8") if remote_url_file.exists() else ""

app = Flask(__name__)
_cv_shazam: ContextVar[Shazam] = ContextVar("shazam")
shazam: Shazam = LocalProxy(_cv_shazam)  # type: ignore


@lru_cache
def _get_shazam(lang):
    """Return a `Shazam` object configured to search in the given language."""
    return Shazam(language=lang or "en-US", endpoint_country="GB" if lang is None else lang.split("-")[0])


@app.before_request
def set_shazam():
    """Automatically create the needed `Shazam` object on every request."""
    _cv_shazam.set(_get_shazam(request.args.get("lang") or session.get("lang")))


@app.after_request
def minify_response(response: Response):
    """Automatically minify HTML responses."""
    if minify_html and response.content_type.split(";")[0] == "text/html":
        try:
            data = response.get_data(as_text=True)
        except RuntimeError:
            # If we can't get the data because it's a stream
            # or because of a wrong encoding, we stop here
            return response
        response.set_data(minify_html.minify(data, minify_css=True, minify_js=True, do_not_minify_doctype=True))
    return response


@app.context_processor
def variables():
    """Variables that are used in many templates."""
    return {
        "lang": session.get("lang", ""),
        "remote_url": remote_url,
    }


@app.route("/")
def home():
    """Home page."""
    return render_template("home.html")


@app.route("/setlang", methods=["GET", "POST"])
def setlang():
    """Store the language in the current session for future requests."""
    lang = request.values.get("lang", "")
    if not lang:
        return render_template("error.html", message="No language specified, please add ?lang=LANGUAGE to the URL.")
    if "-" not in lang:
        lang = f"{lang}-{lang.upper()}"
    session["lang"] = lang
    return redirect(app.url_for("home"))


@app.route("/api/recognize", methods=["POST"])
async def recognize():
    """Recognize a song."""
    file = request.files["file"]

    ffmpeg_path = get_ffmpeg_path()
    # If FFmpeg is already in PATH, immediatly recognize the file
    if ffmpeg_path is None:
        return await shazam.recognize(file.stream.read())

    # Otherwise convert the file to .wav and recognize it
    out = None
    try:
        # Output file
        fd, out = tempfile.mkstemp(".wav")

        # Create a temporary file with the input file...
        with tempfile.NamedTemporaryFile("wb") as f:
            while (chunk := file.stream.read(65536)) != b"":
                f.write(chunk)

            # ...and convert it
            os.close(fd)
            sp.run([ffmpeg_path, "-y", "-i", f.name, out], check=True)

        # Recognize the file
        return await shazam.recognize(out)
    finally:
        # Don't forget to delete the file!
        if out is not None:
            os.remove(out)


app.secret_key = os.getenv("SECRET_KEY", "shazam-api-secret-key")

if __name__ == "__main__":
    app.run(debug=True)
