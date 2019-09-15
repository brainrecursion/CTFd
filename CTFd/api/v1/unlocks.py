from flask import request
from flask_restplus import Namespace, Resource
from CTFd.cache import clear_standings
from CTFd.models import db, get_class_by_tablename, Unlocks, Hints
from CTFd.utils.user import get_current_user
from CTFd.schemas.unlocks import UnlockSchema
from CTFd.schemas.awards import AwardSchema
from CTFd.utils.decorators import (
    during_ctf_time_only,
    require_verified_emails,
    admins_only,
    authed_only,
)

unlocks_namespace = Namespace("unlocks", description="Endpoint to retrieve Unlocks")


@unlocks_namespace.route("")
class UnlockList(Resource):
    @admins_only
    def get(self):
        hints = Unlocks.query.all()
        schema = UnlockSchema()
        response = schema.dump(hints)

        if response.errors:
            return {"success": False, "errors": response.errors}, 400

        return {"success": True, "data": response.data}

    @during_ctf_time_only
    @require_verified_emails
    @authed_only
    def post(self):
        req = request.get_json()
        user = get_current_user()

        req["user_id"] = user.id
        req["team_id"] = user.team_id

        Model = get_class_by_tablename(req["type"])
        target = Model.query.filter_by(id=req["target"]).first_or_404()

        prereq_unlocks = (
            Hints.query
            .filter_by(challenge_id = target.challenge_id)
            .filter(Hints.cost < target.cost)
            .all()
        )
        unlock_ids = (
            Unlocks.query
            .filter_by(account_id=user.account_id)
            .all()
        )
        unlock_ids = set([unlock.target for unlock in unlock_ids])
        prereqs = set([hint.id for hint in prereq_unlocks])
        if (unlock_ids >= prereqs):
            pass
        else:
            return (
                {
                    "success": False,
                    "errors": {
                        "score": "Hints have to be unlocked in cost order"
                    },
                },
                400,
            )
        if target.id in unlock_ids:
            return (
                {
                    "success": False,
                    "errors": {
                        "score": "You have already unlocked this hint"
                    },
                },
                400,
            )
        if target.cost > user.score:
            return (
                {
                    "success": False,
                    "errors": {
                        "score": "You do not have enough points to unlock this hint"
                    },
                },
                400,
            )

        schema = UnlockSchema()
        response = schema.load(req, session=db.session)

        if response.errors:
            return {"success": False, "errors": response.errors}, 400

        db.session.add(response.data)

        award_schema = AwardSchema()
        award = {
            "user_id": user.id,
            "team_id": user.team_id,
            "name": target.name,
            "description": target.description,
            "value": (-target.cost),
            "category": target.category,
        }

        award = award_schema.load(award)
        db.session.add(award.data)
        db.session.commit()
        clear_standings()

        response = schema.dump(response.data)

        return {"success": True, "data": response.data}
