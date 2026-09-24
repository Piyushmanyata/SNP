#!/usr/bin/env bash
set -euo pipefail

: "${DB_NAME:?}" "${RESTIC_PASSWORD:?}" "${RESTIC_REPOSITORY:?}"
dbpath=$(mktemp -d)
trap 'mongod --dbpath "$dbpath" --shutdown >/dev/null 2>&1 || true; rm -rf "$dbpath"' EXIT

snapshot=$(restic snapshots --json --retry-lock 10m --tag snp | jq -c 'max_by(.time) // empty')
[ -n "$snapshot" ] || { echo "DRILL FAILED: no snapshot in $RESTIC_REPOSITORY"; exit 1; }
patients=$(jq -r '.tags[] | select(startswith("patients=")) | ltrimstr("patients=")' <<<"$snapshot")
[ -n "$patients" ] || { echo "DRILL FAILED: snapshot has no patients tag"; exit 1; }

mongod --dbpath "$dbpath" --port 27018 --bind_ip 127.0.0.1 --wiredTigerCacheSizeGB 0.25 \
  --fork --logpath "$dbpath/mongod.log" >/dev/null
restic dump --retry-lock 10m "$(jq -r .id <<<"$snapshot")" snp.archive.gz \
  | mongorestore --uri mongodb://127.0.0.1:27018 --gzip --archive --oplogReplay --quiet

PATIENTS="$patients" mongosh mongodb://127.0.0.1:27018 --quiet --eval '
  const d = db.getSiblingDB(process.env.DB_NAME);
  const failure = (() => {
    const restored = d.patients.countDocuments({});
    if (restored < Number(process.env.PATIENTS)) {
      return `patients: ${restored} restored, ${process.env.PATIENTS} existed when the dump started`;
    }
    const orphan = d.fulfilments.aggregate([
      { $match: { slip_id: { $ne: null } } },
      { $lookup: { from: "deferred_slips", localField: "slip_id", foreignField: "_id", as: "slip" } },
      { $match: { slip: { $size: 0 } } },
      { $limit: 1 },
    ]).toArray()[0];
    if (orphan) return `fulfilment ${orphan._id} points at missing slip ${orphan.slip_id}`;
    const seats = d.ot_schedule_days.aggregate([
      { $lookup: {
        from: "fulfilments", localField: "_id", foreignField: "ot_schedule_day_id", as: "booked",
        pipeline: [{ $match: { item_type: "ot", status: "deferred" } }],
      } },
      { $project: { taken: { $ifNull: ["$seats_taken", 0] }, booked: { $size: "$booked" } } },
      { $match: { $expr: { $ne: ["$taken", "$booked"] } } },
      { $limit: 1 },
    ]).toArray()[0];
    if (seats) return `OT day ${seats._id} has seats_taken ${seats.taken} but ${seats.booked} deferred OT fulfilments`;
    return null;
  })();
  print(failure ? `DRILL FAILED: ${failure}` : "DRILL OK");
  if (failure) quit(1);'
