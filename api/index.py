import sys
import os

# Add the backend directory to sys.path so we can import everything correctly
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app as handler
