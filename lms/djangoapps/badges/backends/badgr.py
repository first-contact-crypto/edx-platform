"""
Badge Awarding backend for Badgr-Server.
"""
import hashlib
import logging
import mimetypes
import json

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from lazy import lazy
from requests.packages.urllib3.exceptions import HTTPError

from badges.backends.base import BadgeBackend
from badges.models import BadgeAssertion
from badges.models import BadgeClass
from eventtracking import tracker

MAX_SLUG_LENGTH = 255
LOGGER = logging.getLogger(__name__)


class BadgrBackend(BadgeBackend):
    """
    Backend for Badgr-Server by Concentric Sky. http://info.badgr.io/
    """
    badges = []

    def __init__(self):
        super(BadgrBackend, self).__init__()
        if not settings.BADGR_API_TOKEN:
            raise ImproperlyConfigured("BADGR_API_TOKEN not set.")

    @lazy
    def _base_url(self):
        """
        Base URL for all API requests.
        """
        return "{}/v2".format(settings.BADGR_BASE_URL)

    # NEW
    def _badgeclasses_url(self, issuer_slug=settings.BADGR_ISSUER_SLUG):
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

    # # # NEW
    # # @lazy
    # # def _backpack_url(self):
    # #   """
    # #   Backpack centric functionality
    # #   """
    # #   return "{}/backpack".format(self._base_url)

    # # NEW
    # @lazy
    # def _issuers_url(self):
    #   """
    #   Issuer centric functionality
    #   """
    #   return "{}/issuers/{}".format(self._base_url, settings.BADGR_ISSUER_SLUG)

    # # NEW
    # @lazy
    # def _issuers_badgeclasses_url(self):
    #     """
    #     """
    #     return "{}/badgeclasses".format(self._issuers_url)

    # # # NEW
    # # @lazy
    # # def _badgeusers_url(self):
    # #   """
    # #   User centric
    # #   """
    # #   return "{}/users/{}".format(self._base_url, settings.BADGR_ISSUER_SLUG)

    # @lazy
    # def _badge_create_url(self):
    #     """
    #     URL for generating a new Badge specification
    #     """
    #     return "{}/badgeclasses".format(self._base_url)

    # def _badge_url(self, slug):
    #     """
    #     Get the URL for a course's badge in a given mode.
    #     """
    #     return "{}/{}".format(self._badge_create_url, slug)

    # def _assertion_url(self, slug):
    #     """
    #     URL for generating a new assertion.
    #     """

        return "{}/assertions".format(self._base_url)

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
        """
        LOGGER.info("BADGE_CLASS: In _create_badge NOW!")
        image = badge_class.image
        # We don't want to bother validating the file any further than making sure we can detect its MIME type,
        # for HTTP. The Badgr-Server should tell us if there's anything in particular wrong with it.
        content_type, __ = mimetypes.guess_type(image.name)
        if not content_type:
            raise ValueError(
                u"Could not determine content-type of image! Make sure it is a properly named .png file. "
                u"Filename was: {}".format(image.name)
            )
        files = {'image': (image.name, image, content_type)}

        data = {
            'name': badge_class.display_name,
            'criteria': badge_class.criteria,
            'description': badge_class.description,
        }

        LOGGER.info("BADGE_APP.. The url is: {} , The headers are: {} , The data is {}".format(self._badgeclasses_url(), self._get_headers(), data))

        result = requests.post(
            self._badgeclasses_url(), headers=self._get_headers(), data=data, files=files, timeout=settings.BADGR_TIMEOUT)

        self._log_if_raised(result, data)

        result_json = result.json()
        LOGGER.info("BADGE_CLASS: In _create_badge() (TYPE OF result.json(): {})..Here is the badgrserver after creating badge: {}".format(type(result_json), result_json))
        LOGGER.info("BADGE_CLASS: In _create_badge() ..The result_json keys are: {}".format(result_json.keys()))

        # try:
        #     if 'entityId' in result_json:
        server_slug = result_json['result'][0]['entityId']
        LOGGER.info("BADGE_CLASS: In _create_badge.. the server_slug is: {}".format(server_slug))
        badge_class.badgr_server_slug = server_slug
        badge_class.save()
        #     else:
        #         LOGGER.info("BADGE_CLASS: In _create_badge() ..What happend? THIS IS WRONG!!!")
        # except Exception as excep:
        #     LOGGER.error('Error on saving Badgr Server Slug of badge_class slug "{0}" with response json "{1}" : {2}'.format(badge_class.slug, result.json(), excep))

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
        uname = user.username + '@firstcontactcrypto.com'
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
            self._assertions_url(server_slug), headers=self._get_headers(), json=data, timeout=settings.BADGR_TIMEOUT
        )
        self._log_if_raised(response, data)

        assertion, _ = BadgeAssertion.objects.get_or_create(user=user, badge_class=badge_class)

        assertion.badge_class = badge_class

        # LOGGER.info("BADGE_CLASS: In _create_assertion.. THE IMAGE URL IS: {}".format(badge_class.img_url))

        assertion.data=response.json()
        assertion.backend='BadgrBackend'
        assertion.image_url = badge_class.image.url 
        LOGGER.info("BADGE_CLASS: In _create_assertion.. the assertion.image_url is: {}".format(assertion.image_url))
        assertion.assertion_url='https://firstcontactcrypto.com/assertion'
        assertion.save()
        return assertion


    @staticmethod
    def _get_headers():
        """
        Headers to send along with the request-- used for authentication.
        """
        return {'Authorization': 'Bearer {}'.format(settings.BADGR_API_TOKEN)}

    def _ensure_badge_created(self, badge_class):
        """
        Verify a badge has been created for this badge class, and create it if not.
        """
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created NOW!")

        server_slug=badge_class.badgr_server_slug
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created the badge_class.badgr_server_slug is: {}".format(server_slug))
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created the type(badgr_server_slug is): {}".format(type(server_slug)))



        if not server_slug:
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..The server_slug IS NOT in badge_class..")
        else:
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..The server_slug IS in badge_class..")
            return

        response=requests.get(self._badgeclasses_url(), headers=self._get_headers(), timeout=settings.BADGR_TIMEOUT)
        status_code=response.status_code
        LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..the status code from 'get badgr server badgeclasesses' is: {}".format(status_code))

        if response.status_code == 200:
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..calling _create_badge NOW!")
            self._create_badge(badge_class)
        else:
            LOGGER.info("BADGE_CLASS: In _ensure_badge_created .. THE RESPONSE STATUS CODE FROM BADGR SERVER IS BAD: {}".format(status_code))
            return

        LOGGER.info("BADGE_CLASS: In _ensure_badge_created ..calling BadgrBackend.badges_append(slug) NOW!.. LEAVING _ensure_badge_created")
        # BadgrBackend.badges.append(slug)

    def award(self, bc, u):
        """
        Make sure the badge class has been created on the backend, and then award the badge class to the user.
        """


        LOGGER.info("BADGE_CLASS: In _award NOW! the user type is: {}".format(type(u)))

        self._ensure_badge_created(bc)
        return self._create_assertion(bc, u, None)
