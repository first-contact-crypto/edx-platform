"""
Badge Awarding backend for Badgr-Server.
"""
import hashlib
import logging
import mimetypes

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
        LOGGER.info("RESPONSE: headers: {}, text: {}".format(response.headers, response.text))
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
        # data = {
        #     'name': badge_class.display_name,
        #     'criteria': badge_class.criteria,
        #     'slug': self._slugify(badge_class),
        #     'description': badge_class.description,
        # }
        data = {
            'name': badge_class.display_name,
            'description': badge_class.description
        }

        result = requests.post(
            self._badgeclasses_url(), headers=self._get_headers(), data=data, files=files,
            timeout=settings.BADGR_TIMEOUT
        )
        self._log_if_raised(result, data)
        try:
            result_json = result.json()
            if 'slug' in result_json:
                badgr_server_slug = result_json['slug']
                badge_class.badgr_server_slug = badgr_server_slug
                badge_class.save()
        except Exception as excep:
            LOGGER.error('Error on saving Badgr Server Slug of badge_class slug "{0}" with response json "{1}" : {2}'.format(badge_class.slug, result.json(), excep))

    def _send_assertion_created_event(self, user, assertion):
        """
        Send an analytics event to record the creation of a badge assertion.
        """
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
        # data = {
        #     'email': user.email,
        #     'evidence': evidence_url,
        # }
        LOGGER.info("CREATE ASSERTION.. the badge_class.slug is: {}".format(badge_class.slug))
        # LOGGER.info("CREATE ASSERTION.. the badge_class.badgeclass_slug is {}".format(badge_class.badgeclass_slug))
        LOGGER.info("CREATE ASSERTION.. the badge_class.badgr_server_slug is: {}".format(badge_class.badgr_server_slug))
        # data = {
        #     'issuer': settings.BADGR_ISSUER_SLUG,
        #     'evidence': {
        #         'url': evidence_url,
        #         'narrative': "You need to pass"
        #     },
        LOGGER.info("CREATE ASSERTION.. user id: {}".format(user.id))
        data = {
            'recipient': {
                'identity': 'johndoe@firstcontactcrypto.com',
                'type': 'email',
                'hashed': False,
                'plaintextIdentity': 'johndoe'
            },
            'badgeclass': badge_class.slug 
        }

        response = requests.post(
            self._assertions_url(badge_class.slug), headers=self._get_headers(), json=data, timeout=settings.BADGR_TIMEOUT
        )
        self._log_if_raised(response, data)

        # assertion, _ = BadgeAssertion.objects.get_or_create(user=user)
        assertion, _ = BadgeAssertion.objects.get_or_create(user=user, badge_class=badge_class)

        assertion.badge_class = badge_class

        # try:
        #     assertion = BadgeAssertion.objects.get(user=user, badge_class=badge_class)
        # except BadgeAssertion.DoesNotExist:
        #     assertion = BadgeAssertion(user=user, badge_class=badge_class)
        #     assertion.save()


        assertion.data = response.json()
        assertion.backend = 'BadgrBackend'
        assertion.image_url = assertion.data['image']
        assertion.assertion_url = assertion.data['json']['id']
        assertion.save()
        self._send_assertion_created_event(user, assertion)
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
        slug = badge_class.badgr_server_slug
        if slug in BadgrBackend.badges:
            return
        response = requests.get(self._badgeclasses_url(), headers=self._get_headers(), timeout=settings.BADGR_TIMEOUT)
        if response.status_code != 200:
            self._create_badge(badge_class)
        BadgrBackend.badges.append(slug)

    def award(self, badge_class, user, evidence_url=None):
        """
        Make sure the badge class has been created on the backend, and then award the badge class to the user.
        """
        self._ensure_badge_created(badge_class)
        return self._create_assertion(badge_class, user, evidence_url)
