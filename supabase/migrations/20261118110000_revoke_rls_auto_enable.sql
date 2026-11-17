-- Keep Supabase's RLS auto-enable helper out of the Data API.
--
-- Projects created with "automatically enable RLS" get public.rls_auto_enable(), a
-- SECURITY DEFINER function run by the ensure_rls event trigger after DDL. It is not
-- part of this repository's schema, but as a function in the exposed public schema it
-- was executable by anon and authenticated through /rest/v1/rpc (Supabase security
-- advisor lints 0028 and 0029). Only the event trigger needs it; revoking EXECUTE does
-- not stop the trigger, which runs as the function's owner.
--
-- A database without the function (CI, local) is left unchanged.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end;
$$;
