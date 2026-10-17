begin;
select plan(8);

select has_table('public', 'runs', 'runs table exists');
select ok(
  (select relrowsecurity from pg_class where oid = 'public.runs'::regclass),
  'RLS is enabled on runs'
);

select lives_ok(
  $$insert into public.runs(status, label_a, label_b, files_a, files_b)
    values ('done', 'pgtap-a', 'pgtap-b', '{"a.md":"# a"}', '{"a.md":"# b"}')$$,
  'a valid run can be inserted'
);
select throws_ok(
  $$insert into public.runs(status, label_a, label_b, files_a, files_b)
    values ('bogus', 'a', 'b', '{}', '{}')$$,
  '23514', null, 'an unknown status is rejected'
);
select throws_ok(
  $$insert into public.runs(status, label_a, label_b, files_a, files_b)
    values ('done', repeat('x', 101), 'b', '{}', '{}')$$,
  '23514', null, 'a label over 100 characters is rejected'
);

set local role anon;
select throws_ok('select 1 from public.runs', '42501', null, 'anon cannot read runs');
reset role;

set local role authenticated;
select throws_ok(
  $$insert into public.runs(status, label_a, label_b, files_a, files_b)
    values ('done', 'a', 'b', '{}', '{}')$$,
  '42501', null, 'authenticated cannot write runs'
);
reset role;

-- Counts only this test's own rows, so data already in the database cannot change the result.
select is(
  (select count(*)::int from public.runs where label_a = 'pgtap-a'),
  1,
  'only the valid insert was stored'
);

select * from finish();
rollback;
