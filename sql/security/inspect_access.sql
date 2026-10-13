-- READ ONLY. Metadata and counts only, never account IDs or payloads.
BEGIN READ ONLY;
SELECT current_database(), current_user, session_user;
SELECT version_num FROM public.alembic_version;
SELECT count(*) AS existing_user_count FROM public.app_users;
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, c.relrowsecurity,
       c.relforcerowsecurity, c.relacl
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','S') ORDER BY c.relname;
SELECT * FROM pg_policies WHERE schemaname='public';
SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
       rolreplication, rolbypassrls FROM pg_roles
WHERE rolname IN ('anon','authenticated','postgres','supabase_admin',
                 'event_radar_api','event_radar_research','event_radar_migrator');
SELECT pg_get_userbyid(roleid) AS granted_role, pg_get_userbyid(member) AS member,
       admin_option, inherit_option, set_option FROM pg_auth_members;
SELECT pg_get_userbyid(defaclrole) AS creator, defaclnamespace::regnamespace AS schema,
       defaclobjtype, defaclacl FROM pg_default_acl;
SELECT nspname, pg_get_userbyid(nspowner) AS owner, nspacl FROM pg_namespace
WHERE nspname='public';
SELECT p.oid::regprocedure, pg_get_userbyid(p.proowner) AS owner, p.prosecdef,
       p.proacl, p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.proname IN ('reject_user_context_mutation',
 'protect_curation_job','protect_weekend_packet','protect_delivery_binding',
 'protect_delivery_attempt','protect_delivery_challenge','protect_delivery_intent');
SELECT r.rolname, c.relname, v.permission,
       has_table_privilege(r.oid,c.oid,v.permission) AS effective
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),('TRUNCATE'),
                   ('REFERENCES'),('TRIGGER')) v(permission)
WHERE n.nspname='public' AND c.relkind='r'
AND r.rolname IN ('anon','authenticated','event_radar_api','event_radar_research')
ORDER BY 1,2,3;
SELECT r.rolname,c.relname,a.attname,
       has_column_privilege(r.oid,c.oid,a.attnum,'SELECT,INSERT,UPDATE,REFERENCES') AS any_access
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
WHERE n.nspname='public' AND c.relkind='r' AND r.rolname IN ('anon','authenticated');
COMMIT;
