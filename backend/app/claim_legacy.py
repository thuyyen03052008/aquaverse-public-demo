"""Local-only explicit ownership assignment of PRE-ACCOUNT farms.

Never run against a shared/remote database. Always make a verified backup first.
Examples:
  python -m app.claim_legacy --email you@example.com
  python -m app.claim_legacy --email you@example.com --confirm
"""

import argparse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_engine, init_database
from .auth_models import FarmOwnership, User
from .models import Farm


def main():
    parser = argparse.ArgumentParser(description='Explicitly claim legacy unowned farms for an existing user')
    parser.add_argument('--email', required=True)
    parser.add_argument('--confirm', action='store_true', help='Writes ownership mapping; otherwise dry run only')
    args = parser.parse_args()
    init_database()
    with Session(get_engine()) as db:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            raise SystemExit('ERROR: Register/login the target account via the app before running claim')
        farms = db.scalars(select(Farm).outerjoin(FarmOwnership, Farm.id == FarmOwnership.farm_id).where(FarmOwnership.farm_id.is_(None)).order_by(Farm.id)).all()
        print(f'Target account: {user.email} (ID {user.id})')
        print(f'Legacy farms awaiting an owner: {len(farms)}')
        for farm in farms:
            print(f'  #{farm.id}: {farm.name} — {farm.region or "no region"}')
        if not args.confirm:
            print('DRY RUN ONLY. To proceed after verifying the list and backup, add --confirm.')
            return
        for farm in farms:
            db.add(FarmOwnership(farm_id=farm.id, user_id=user.id))
        db.commit()
        print(f'CLAIMED {len(farms)} farms. Existing cycle, journal, scenario and batch records remain unchanged.')


if __name__ == '__main__':
    main()
