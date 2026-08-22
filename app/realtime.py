from datetime import datetime

from sqlalchemy import event, text

_deja_enregistre = False


def _contient_changement_pertinent(session, AppState):
    changements = list(session.new) + list(session.dirty) + list(session.deleted)
    return any(not isinstance(obj, AppState) for obj in changements)


def register(app, db):
    """Écoute chaque commit et met à jour AppState.last_modified_at dès qu'une donnée
    autre que AppState lui-même a changé, pour permettre aux pages de détecter
    qu'il faut se rafraîchir sans avoir à instrumenter chaque route manuellement."""
    global _deja_enregistre
    if _deja_enregistre:
        return
    _deja_enregistre = True

    from app.models import AppState

    @event.listens_for(db.session, "before_commit")
    def _detecter_changement(session):
        session.info["sas_dirty"] = _contient_changement_pertinent(session, AppState)

    @event.listens_for(db.session, "after_commit")
    def _bump_version(session):
        if not session.info.pop("sas_dirty", False):
            return
        # On passe par une connexion séparée (pas db.session) : une session ORM ne
        # peut pas émettre de nouvelle requête juste après son propre commit.
        maintenant = datetime.utcnow()
        with db.engine.begin() as connexion:
            resultat = connexion.execute(
                text("UPDATE app_state SET last_modified_at = :ts WHERE id = 1"), {"ts": maintenant}
            )
            if resultat.rowcount == 0:
                connexion.execute(
                    text("INSERT INTO app_state (id, last_modified_at) VALUES (1, :ts)"), {"ts": maintenant}
                )
