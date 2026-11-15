-- =========================================================================
-- MNEMOS — development seed
--
-- Intentionally empty of user data. Creating auth users requires the
-- Supabase Auth API (not plain SQL), so development accounts are created
-- through the application or `supabase auth` tooling.
--
-- When a user is created, the on_auth_user_created trigger provisions:
--   * public.profiles row
--   * public.user_preferences row
--   * a default 'Personal' workspace (+ owner membership)
--
-- Do not add fabricated knowledge, conversations or activity here.
-- =========================================================================

-- No-op statement so the file is a valid SQL script.
select 'MNEMOS seed: no development data is inserted by design.' as note;
