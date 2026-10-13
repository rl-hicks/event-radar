-- READ ONLY post-commit assertions. Count only, never user identities/private content.
BEGIN READ ONLY;
DO $$
DECLARE t text; r text; f text; o oid;
BEGIN
  IF (SELECT version_num FROM public.alembic_version) <> '0006_hosted_access_hardening' THEN
    RAISE EXCEPTION 'Unexpected migration revision';
  END IF;
  FOREACH t IN ARRAY ARRAY['alembic_version','app_users','regional_universes',
    'regional_universe_snapshots','regional_research_runs','user_context_revisions',
    'curation_jobs','weekend_packets','delivery_bindings','delivery_challenges',
    'delivery_intents','delivery_attempts'] LOOP
    o := to_regclass('public.'||t);
    IF o IS NULL OR NOT EXISTS(SELECT FROM pg_class WHERE oid=o AND relrowsecurity
        AND relowner=(SELECT oid FROM pg_roles WHERE rolname='event_radar_migrator')) THEN
      RAISE EXCEPTION 'Missing table, RLS or ownership mismatch';
    END IF;
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
      IF has_any_column_privilege(r,o,'SELECT,INSERT,UPDATE,REFERENCES')
         OR has_table_privilege(r,o,'DELETE,TRUNCATE,TRIGGER') THEN
        RAISE EXCEPTION 'Effective browser access remains';
      END IF;
    END LOOP;
  END LOOP;
  FOREACH r IN ARRAY ARRAY['event_radar_api','event_radar_research'] LOOP
    IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname=r AND NOT rolsuper AND NOT rolcanlogin
       AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication)
       OR EXISTS(SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=r))
       OR has_database_privilege(r,current_database(),'CREATE')
       OR has_schema_privilege(r,'public','CREATE')
       OR has_any_column_privilege(r,'public.alembic_version','SELECT,INSERT,UPDATE,REFERENCES') THEN
      RAISE EXCEPTION 'Runtime role configuration mismatch';
    END IF;
  END LOOP;
  FOREACH f IN ARRAY ARRAY['reject_user_context_mutation','protect_curation_job',
    'protect_weekend_packet','protect_delivery_binding','protect_delivery_attempt',
    'protect_delivery_challenge','protect_delivery_intent'] LOOP
    FOREACH r IN ARRAY ARRAY['anon','authenticated','event_radar_api','event_radar_research'] LOOP
      IF has_function_privilege(r,'public.'||f||'()','EXECUTE') THEN
        RAISE EXCEPTION 'Application function is directly executable';
      END IF;
    END LOOP;
  END LOOP;
END $$;
SELECT count(*) AS preserved_user_count FROM public.app_users;
SELECT count(*) AS application_trigger_count FROM pg_trigger
WHERE NOT tgisinternal AND tgrelid IN (
 SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace
 AND relname IN ('user_context_revisions','curation_jobs','weekend_packets',
 'delivery_bindings','delivery_challenges','delivery_intents','delivery_attempts'));
COMMIT;
