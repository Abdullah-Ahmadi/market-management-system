import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexityValidator:
    """Require the same core password rules shown by the live UI checklist."""

    def validate(self, password, user=None):
        missing = []
        if not re.search(r'[A-Z]', password):
            missing.append('one uppercase letter')
        if not re.search(r'[a-z]', password):
            missing.append('one lowercase letter')
        if not re.search(r'\d', password):
            missing.append('one number')
        if not re.search(r'[^A-Za-z0-9]', password):
            missing.append('one symbol')
        if missing:
            raise ValidationError(_('Password must contain at least %(requirements)s.'), code='password_complexity', params={'requirements': ', '.join(missing)})

    def get_help_text(self):
        return _('Your password must include uppercase and lowercase letters, a number, and a symbol.')


def password_similar_to_username(password, username):
    """Non-blocking similarity signal used for UI/server warnings."""
    password = (password or '').lower().strip()
    username = (username or '').lower().strip()
    if not password or not username:
        return False
    compact = re.sub(r'[^a-z0-9]', '', password)
    user_compact = re.sub(r'[^a-z0-9]', '', username)
    if len(user_compact) >= 3 and user_compact in compact:
        return True
    # Deliberately simple and explainable: several matching username characters
    # at the beginning/end should warn, but never block the password.
    common = sum(1 for a, b in zip(compact, user_compact) if a == b)
    return len(user_compact) >= 4 and common / max(1, len(user_compact)) >= 0.6
