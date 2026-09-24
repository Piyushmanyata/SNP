const dbName = process.env.DB_NAME;

db.getSiblingDB(dbName).createUser({
  user: "snp_app",
  pwd: process.env.MONGO_APP_PASSWORD,
  roles: [{ role: "readWrite", db: dbName }],
});

db.getSiblingDB("admin").createUser({
  user: "snp_backup",
  pwd: process.env.MONGO_BACKUP_PASSWORD,
  roles: ["backup", "restore"],
});
