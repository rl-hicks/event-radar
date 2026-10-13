-- PREPARED ONLY. Separately approved, committed security containment before upgrade.
-- Run on the verified E0 target only; this changes no application-user rows.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DO $$
DECLARE t text; r text; cols text;
BEGIN
  IF (SELECT version_num FROM public.alembic_version) <> '0001_app_users' THEN
    RAISE EXCEPTION 'Expected reviewed E0 revision';
  END IF;
  FOREACH t IN ARRAY ARRAY['app_users','alembic_version'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
    SELECT string_agg(quote_ident(column_name),',') INTO cols FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t;
    FOREACH r IN ARRAY ARRAY['PUBLIC','anon','authenticated'] LOOP
      IF r='PUBLIC' OR EXISTS(SELECT FROM pg_roles WHERE rolname=r) THEN
        EXECUTE format('REVOKE ALL ON public.%I FROM %s',t,
          CASE WHEN r='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r) END);
        EXECUTE format('REVOKE SELECT (%s), INSERT (%s), UPDATE (%s), REFERENCES (%s) '
          'ON public.%I FROM %s',cols,cols,cols,cols,t,
          CASE WHEN r='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(r) END);
      END IF;
    END LOOP;
  END LOOP;
  FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
    IF EXISTS(SELECT FROM pg_roles WHERE rolname=r) THEN
      FOREACH t IN ARRAY ARRAY['app_users','alembic_version'] LOOP
        IF has_any_column_privilege(r,'public.'||t,'SELECT,INSERT,UPDATE,REFERENCES')
           OR has_table_privilege(r,'public.'||t,'DELETE,TRUNCATE,TRIGGER') THEN
          RAISE EXCEPTION 'Inherited client privileges require separate remediation';
        END IF;
      END LOOP;
    END IF;
  END LOOP;
END $$;
COMMIT;
