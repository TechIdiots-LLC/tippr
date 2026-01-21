# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
###############################################################################


import secrets
import string

from pylons import app_globals as g

# Use the modern 'captcha' package (pip install captcha) instead of pycaptcha
from captcha.image import ImageCaptcha

IDEN_LENGTH = 32
SOL_LENGTH = 6

# Create a reusable ImageCaptcha instance with dimensions matching original (120x50)
_captcha_generator = ImageCaptcha(width=120, height=50)


def _random_identifier(alphabet=string.ascii_letters + string.digits, length=32):
    """Generate a random identifier string.

    Replaces pycaptcha's randomIdentifier with a secure Python 3 implementation.
    """
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_iden():
    return _random_identifier(length=IDEN_LENGTH)


def make_solution():
    return _random_identifier(alphabet=string.ascii_letters, length=SOL_LENGTH).upper()


def get_image(iden):
    """Generate a CAPTCHA image for the given identifier.

    Returns a PIL Image object.
    """
    key = "captcha:%s" % iden
    solution = g.gencache.get(key)
    if not solution:
        solution = make_solution()
        g.gencache.set(key, solution, time=300)

    # Generate image using the modern captcha library
    # generate_image returns a PIL Image object
    return _captcha_generator.generate_image(solution)


def valid_solution(iden, solution):
    key = "captcha:%s" % iden

    if (not iden or
            not solution or
            len(iden) != IDEN_LENGTH or
            len(solution) != SOL_LENGTH or
            solution.upper() != g.gencache.get(key)):
        # the guess was wrong so make a new solution for the next attempt--the
        # client will need to refresh the image before guessing again
        solution = make_solution()
        g.gencache.set(key, solution, time=300)
        return False
    else:
        g.gencache.delete(key)
        return True
