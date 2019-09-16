from .models import ExtraInfo
from django.forms import ModelForm

class ExtraInfoForm(ModelForm):
    """
    The fields on this form are derived from the ExtraInfo model in models.py.
    """
    def __init__(self, *args, **kwargs):
        super(ExtraInfoForm, self).__init__(*args, **kwargs)
        self.fields['promo_code'].error_messages = {
            "optional": u"Please submit Promo Code.",
            "invalid": u"Not an applicable answer",
        }

    class Meta(object):
        model = ExtraInfo
        fields = ('promo_code',)
