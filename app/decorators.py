from functools import wraps

from flask import abort
from flask_login import login_required, current_user

# Modules accessibles pour chaque rôle non-admin. Le rôle "admin" a toujours accès à tout.
# Seul "admin" peut lancer/gérer les appels de présence ("presence") ; comptable et
# secrétaire doivent en revanche confirmer leur propre présence comme un employé.
ROLE_MODULES = {
    "comptable": {"dashboard", "depenses", "compte_bancaire", "fournisseurs", "salaires_paiement"},
    "secretaire": {"dashboard", "rapports", "salaires", "consommables", "agenda"},
    "agent_commercial": {"dashboard", "commercial"},
}

# Rôles qui doivent valider leur propre présence lors d'un appel (en plus des employés).
ROLES_DOIVENT_CONFIRMER_PRESENCE = {"comptable", "secretaire", "employe", "agent_commercial"}


def admin_required(view):
    """Réserve l'accès aux comptes de rôle 'admin' uniquement (actions sensibles)."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (getattr(current_user, "is_admin_account", False) and current_user.role == "admin"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def role_required(*modules):
    """Autorise les comptes admin (toujours) et les comptes dont le rôle donne accès à l'un des modules listés."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not getattr(current_user, "is_admin_account", False):
                abort(403)
            if current_user.role == "admin":
                return view(*args, **kwargs)
            allowed = ROLE_MODULES.get(current_user.role, set())
            if not allowed.intersection(modules):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def confirmation_presence_required(view):
    """Autorise les employés (portail présence) et les comptes comptable/secrétaire
    (qui doivent aussi valider leur présence), mais pas les comptes admin."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if getattr(current_user, "is_admin_account", False):
            if current_user.role not in ROLES_DOIVENT_CONFIRMER_PRESENCE:
                abort(403)
        return view(*args, **kwargs)
    return wrapped


def espace_employe_required(view):
    """Autorise les employés (portail dédié) et les comptes comptable/secrétaire à accéder
    à leurs propres pages libre-service (présence, appareils...), mais pas les comptes admin."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if getattr(current_user, "is_admin_account", False):
            if current_user.role not in ROLES_DOIVENT_CONFIRMER_PRESENCE:
                abort(403)
        return view(*args, **kwargs)
    return wrapped
