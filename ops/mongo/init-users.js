const dbName = process.env.DB_NAME;

db.getSiblingDB(dbName).createUser({
  user: "snp_app",
  pwd: process.env.MONGO_APP_PASSWORD,
  roles: [{ role: "readWrite", db: dbName }],
});

db.getSiblingDB("admin").createRole({
  role: "snpOpsStatusWriter",
  privileges: [{ resource: { db: dbName, collection: "ops_status" }, actions: ["find", "insert", "update"] }],
  roles: [],
});

db.getSiblingDB("admin").createUser({
  user: "snp_backup",
  pwd: process.env.MONGO_BACKUP_PASSWORD,
  roles: ["backup", "snpOpsStatusWriter"],
});
