drop if exists vt;

create table vt (vec vector);

insert into vt (vec) values('[1,2,3,4,5,6,7,7]');
insert into vt (vec) values('[1234,12341234,123412341234,1234123412341234.1234]');
insert into vt (vec) values('[3,3,3,3.5,2.4]');
insert into vt (vec) values('[1.0, 2.0, 3.0]');
insert into vt (vec) values('[1.1111, 2.2222, 3.3333, 4.4444]');
insert into vt (vec) values('[0.1, 0.01, 0.001, 0.0001]');

-- Scientific notation
insert into vt (vec) values('[1.234e-5, 1.234e5, 1.234e10]');
insert into vt (vec) values('[1E-10, 1E10, 1E-3]');

-- Mixed integer and float
insert into vt (vec) values('[1, 2.5, 3, 4.75, 5]');

-- Negative numbers
insert into vt (vec) values('[-1.5, -2.25, -3.75]');
insert into vt (vec) values('[-0.001, -0.002, -0.003]');

-- Edge cases
insert into vt (vec) values('[0.0, -0.0, 1.0, -1.0]');
insert into vt (vec) values('[9999999.9999999, -9999999.9999999]');

-- Whitespace handling
insert into vt (vec) values('[  1.5  ,  2.5  ,  3.5  ]');
insert into vt (vec) values('[1.1,    2.2,   3.3   ]');

-- Precision tests
insert into vt (vec) values('[1.123456789, 2.123456789, 3.123456789]');
insert into vt (vec) values('[0.000000001, 0.999999999]');

-- Mixed precision
insert into vt (vec) values('[1.1, 2.22, 3.333, 4.4444, 5.55555]');
