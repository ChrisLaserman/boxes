import os

# Tests compare against upstream reference output, so keep the local
# machine profile out of them.
os.environ["BOXES_PROFILE"] = os.devnull
