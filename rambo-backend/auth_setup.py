"""Run this script ONCE on your machine to authenticate with Google.
It opens a browser, you log in, and it saves token.json for R.A.M.B.O to use.

Usage: python auth_setup.py
"""

from google_auth import run_auth_flow, is_authenticated

if is_authenticated():
    print("Already authenticated with Google.")
else:
    print("Opening browser for Google sign-in...")
    run_auth_flow()
    print("Authenticated. token.json saved.")
