// Runs once, on first start of an empty data volume (official mongo image convention).
// Creates a least-privilege application user: owner of the app and test databases only,
// no access to admin/other databases. Collections, validators and indexes are applied by the
// backend itself at startup (app/db_schema.py).
const user = process.env.MONGO_APP_USER;
const pwd = process.env.MONGO_APP_PASSWORD;
const dbName = process.env.MONGO_APP_DB || "printbot";
if (!user || !pwd) throw new Error("MONGO_APP_USER / MONGO_APP_PASSWORD must be set");

db = db.getSiblingDB(dbName);
db.createUser({
  user,
  pwd,
  roles: [
    { role: "dbOwner", db: dbName },
    { role: "dbOwner", db: dbName + "_test" },
  ],
});
