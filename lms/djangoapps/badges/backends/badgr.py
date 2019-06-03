"""
Badge Awarding backend for Badgr-Server.

EPIPHANY BADGE SERVER SLUG: V_MaSinhQJeKGOtZz6tDAQ
IMAGE: https://media.us.badgr.io/uploads/badges/issuer_badgeclass_efc20af1-7d43-4d1e-877e-447244ea3fd3.png

COURSE BADGE SERVER SLUG: 2gnNK3RZSlOutOrVeQlD_A
IMAGE: https://media.us.badgr.io/uploads/badges/issuer_badgeclass_63237c1a-3f3d-40b7-9e48-085658d2799f.png

REDEMPTION BADGE SERVER SLUG: XrG4QUcyTQGVch1VipS-Qw
IMAGE: https://media.us.badgr.io/uploads/badges/issuer_badgeclass_41b742a0-d58c-4223-bffb-f2bc92fdd4bf.png

"""
import hashlib
import logging
import mimetypes
import json
import os

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from lazy import lazy
from requests.packages.urllib3.exceptions import HTTPError

from badges.backends.base import BadgeBackend
from badges.models import BadgeAssertion
from badges.models import BadgeClass
from django.db.models import ImageField
from eventtracking import tracker

MAX_SLUG_LENGTH = 255
LOGGER = logging.getLogger(__name__)

EPIPHANY_BADGR_SLUG = 'V_MaSinhQJeKGOtZz6tDAQ'
BADGR_ISSUER_SLUG = 'rGy5MNWtQgSs1vfnLyPlmg'


class BadgrBackend(BadgeBackend):
    """
    Backend for Badgr-Server by Concentric Sky. http://info.badgr.io/
    """
    badgr_badgeclass_list = None
    access_token_cls = ''
    refresh_token_cls = ''

    def __init__(self):
        super(BadgrBackend, self).__init__()
        # trigger class variables being initialized:
        self.access_token
        self.refresh_token

    @lazy
    def _base_url(self):
        """
        Base URL for all API requests.
        """
        LOGGER.info("BADGE_CLASS: In _base_url.. the settings.BADGR_BASE_URL is: {}".format(settings.BADGR_BASE_URL))
        return "{}/v2".format(settings.BADGR_BASE_URL)

    @property
    def access_token(self):
        fname = '/openedx/data/uploads/badgr/badgr.json'
        at = None
        with open(fname, 'r') as f:
            info = json.load(f)
            at = info['badgr_access_token']
            BadgrBackend.access_token_cls = at
        return at

    @property
    def refresh_token(self):
        fname = '/openedx/data/uploads/badgr/badgr.json'
        rt = None
        with open(fname, 'r') as f:
            info = json.load(f)
            rt = info['badgr_refresh_token']
            BadgrBackend.refresh_token_cls = rt
        return rt

    def _get_new_access_token(self, badge_class):
        """
        Calls the badgr server
        """
        LOGGER.info("BADGE_CLASS: In _get_new_access_token.. NOW!")
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }

        response = requests.post(
            self._refresh_token_url(), json=data, timeout=settings.BADGR_TIMEOUT
        )

        if response.status_code == 200:
            data = response.json()
            fname = '/openedx/data/uploads/badgr/badgr.json'
            at = data['access_token']
            rt = data['refresh_token']
            tokens = {'badgr_access_token': at, 'refresh_token': rt}
            with open(fname, 'w') as f:
                json.dump(tokens, f)
            self._ensure_badge_created(badge_class)
        else:
            LOGGER.error("BADGE_CLASS: In _get_new_access_token .. cannot get new access token using refresh token.. CANNOT AUTHENTICATE !!!!!!!!")
        
        return response.status_code

    # NEW
    def _badgeclasses_url(self, issuer_slug=BADGR_ISSUER_SLUG):
        """
        Badge Class centric functionality.
        """
        return "{}/issuers/{}/badgeclasses".format(self._base_url, issuer_slug)

        # NEW

    def _assertions_url(self, badge_slug):
        """
        Assertions centric functionality
        """
        return "{}/badgeclasses/{}/assertions".format(self._base_url, badge_slug)

    def _refresh_token_url(self):
        """
        Get a new access token using the refresh token. Get and set from settings.
        """
        return "https://api.badgr.io/o/token".format(self._base_url)

    def _slugify(self, badge_class):
        """
        Get a compatible badge slug from the specification.
        """
        LOGGER.info("BADGE_CLASS: In _slugify NOW!")

        slug = badge_class.issuing_component + badge_class.slug
        if badge_class.issuing_component and badge_class.course_id:
            # Make this unique to the course, and down to 64 characters.
            # We don't do this to badges without issuing_component set for backwards compatibility.
            slug = hashlib.sha256(slug + unicode(badge_class.course_id)).hexdigest()
        if len(slug) > MAX_SLUG_LENGTH:
            # Will be 64 characters.
            slug = hashlib.sha256(slug).hexdigest()
        return slug

    def _log_if_raised(self, response, data):
        """
        Log server response if there was an error.
        """
        LOGGER.info("BADGE_CLASS: In _log_if_raised.. RESPONSE: headers: {}, text: {}".format(response.headers, response.text))
        try:
            response.raise_for_status()
        except HTTPError:
            LOGGER.error(
                u"Encountered an error when contacting the Badgr-Server. Request sent to %r with headers %r.\n"
                u"and data values %r\n"
                u"Response status was %s.\n%s",
                response.request.url, response.request.headers,
                data,
                response.status_code, response.content
            )
            raise


    def _create_badge(self, badge_class):
        """
        Create the badge class on Badgr.        
        
        EPIPHANY BADGE SERVER SLUG: V_MaSinhQJeKGOtZz6tDAQ
        IMAGE: https: // media.us.badgr.io / uploads / badges / issuer_badgeclass_efc20af1 - 7d43 - 4d1e - 877e-447244ea3fd3.png

        COURSE BADGE SERVER SLUG: 2gnNK3RZSlOutOrVeQlD_A
        IMAGE: https: // media.us.badgr.io / uploads / badges / issuer_badgeclass_63237c1a - 3f3d - 40b7 - 9e48 - 085658d2799f.png
        """

        LOGGER.info("BADGE_CLASS: In _create_badge NOW!")

        server_slug = None
        image_url = None

        if badge_class.slug == 'course':
            server_slug = '2gnNK3RZSlOutOrVeQlD_A'
            image_url = 'https//media.us.badgr.io/uploads/badges/issuer_badgeclass_63237c1a-3f3d-40b7-9e48-085658d2799f.png'
            # GET BADGR IMAGE
            image = requests.get(image_url, timeout=settings.BADGR_TIMEOUT)
            with open('/openedx/data/uploads/badgr/images/course-badge.png', 'wb') as f:
                f.write(image)
            badge_class.image = models.ImageField('badgr/images/course-badge.png')
        else:
            server_slug = 'V_MaSinhQJeKGOtZz6tDAQ'
            image_url = 'https://media.us.badgr.io/uploads/badges/issuer_badgeclass_efc20af1-7d43-4d1e-877e-447244ea3fd3.png'
            # GET BADGR IMAGE
            image = requests.get(image_url, timeout=settings.BADGR_TIMEOUT)
            with open('/openedx/data/uploads/badgr/images/epiphany-badge.png', 'wb') as f:
                f.write(image)
            badge_class.image = models.ImageField('badgr/images/epiphany-badge.png')

        badge_class.badgr_server_slug = server_slug
        badge_class.image_url = image_url
        badge_class.save()


    def _send_assertion_created_event(self, user, assertion):
        """
        Send an analytics event to record the creation of a badge assertion.
        """
        LOGGER.info("BADGE_CLASS: In _send_assertion_created_event NOW!")

        tracker.emit(
            'edx.badge.assertion.created', {
                'user_id': user.id,
                'badge_slug': assertion.badge_class.slug,
                'badge_badgr_server_slug': assertion.badge_class.badgr_server_slug,
                'badge_name': assertion.badge_class.display_name,
                'issuing_component': assertion.badge_class.issuing_component,
                'course_id': unicode(assertion.badge_class.course_id),
                'enrollment_mode': assertion.badge_class.mode,
                'assertion_id': assertion.id,
                'assertion_image_url': assertion.image_url,
                'assertion_json_url': assertion.assertion_url,
                'issuer': assertion.data.get('issuer'),
            }
        )

    def _create_assertion(self, badge_class, user, evidence_url):
        """
        Register an assertion with the Badgr server for a particular user for a specific class.
        """
        uname = user.email
        ptid = user.username
        LOGGER.info("BADGE_CLASS: In _create_assertion.. the user.username;user.email is: {} ~~ {}".format(user.username, user.email))
        data = {
            'recipient': {
                'identity': uname,
                'type': 'email',
                'hashed': False,
                'plaintextIdentity': ptid
            }
        }
        server_slug = badge_class.badgr_server_slug
        LOGGER.info("BADGE_CLASS In _create_assertion the server_slug is: {}".format(server_slug))
        LOGGER.info("BADGE_CLASS In _create_assertion.. the data being sent is: {}".format(data))
        response = requests.post(
            self._assertions_url(server_slug), headers=self._get_headers(), json=data, timeout=settings.BADGR_TIMEOUT)
        self._log_if_raised(response, data)

        assertion, _ = BadgeAssertion.objects.get_or_create(user=user, badge_class=badge_class, data=response.json())
        # LOGGER.info("BADGE_CLASS: In _create_assertion.. THE IMAGE URL IS: {}".format(badge_class.img_url))
        assertion.backend='BadgrBackend'
        assertion.server_slug = response.json().result[0].entityId
        assertion.image_url = badge_class.image_url 
        LOGGER.info("BADGE_CLASS: In _create_assertion.. the assertion.image_url is: {}".format(assertion.image_url))
        assertion.assertion_url='https://firstcontactcrypto.com/assertions/epiphany.html'
        assertion.save()
        return assertion


    @staticmethod
    def _get_headers():
        """
        Headers to send along with the request-- used for authentication.
        """
        LOGGER.info("BADGE_CLASS: In _get_headers.. the BADGR_API_TOKEN length is: {} .. and the TOKEN is: {}".format(len(BadgrBackend.access_token_cls), BadgrBackend.access_token_cls))
        return {'Authorization': 'Bearer {}'.format(BadgrBackend.access_token_cls)}

    def _ensure_badge_created(self, badge_class):
        """
        Verify a badge has been created for this badge class, and create it if not.
        """
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created NOW!")

        server_slug=badge_class.badgr_server_slug
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created the badge_class.badgr_server_slug is: {}".format(server_slug))
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created the type(badgr_server_slug is): {}".format(type(server_slug)))

        # Check if the in-house db has the badgr server_slug.. if not create a new badge on badgr server ...... WRONG! FIX ME
        if not server_slug:
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..The server_slug IS NOT in badge_class..")
        else:
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..The server_slug IS in badge_class..")
            return

        response=requests.get(self._badgeclasses_url(), headers=self._get_headers(), timeout=settings.BADGR_TIMEOUT)
        status_code=response.status_code
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..the status code from 'get badgr server badgeclasesses' is: {}".format(status_code))

        if response.status_code == 200:
            BadgrBackend.badgr_badgeclass_list = json.loads(response)['result']
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created.. here is the badgr_badgeclass_list: {}".format(BadgeBackend.badgr_badgeclass_list))
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..calling _create_badge NOW!")
            self._create_badge(badge_class)
        else:
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created .. THE RESPONSE STATUS CODE FROM BADGR SERVER IS BAD: {}".format(status_code))
            # LOGGER.info("BADGE_CLASS: In _ensure_badge_created .. THE REPONSE HEADER IS: {}".format(response.headers)
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created .. Trying refresh access token now...")
            ret_code = self._get_new_access_token(badge_class)
            if not ret_code == 200:
                LOGGER.error("BADGR.PY: In _ensure_badge_created.. ERROR: Could not refresh the badgr token!")
                return
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..calling BadgrBackend.badges_append(slug) NOW!.. LEAVING _ensure_badge_created")


    def award(self, bc, u):
        """
        Make sure the badge class has been created on the backend, and then award the badge class to the user.
        """

        LOGGER.info("BADGE_CLASS: In _award NOW! the user type is: {}".format(type(u)))

        self._ensure_badge_created(bc)
        return self._create_assertion(bc, u, None)


