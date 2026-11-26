USE demo;

CREATE TABLE IF NOT EXISTS widgets (
    id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

INSERT INTO widgets (id, name) VALUES
    (1, 'alpha'),
    (2, 'beta');

CREATE TABLE IF NOT EXISTS zz_secret (
    id INT PRIMARY KEY,
    token VARCHAR(50) NOT NULL
);

INSERT INTO zz_secret (id, token) VALUES (1, 'hidden');

-- The password exercises #, spaces, double quotes, a backslash, and $.
CREATE USER IF NOT EXISTS 'sink'@'%'
    IDENTIFIED WITH mysql_native_password BY 'p#ass "word" \\ $ecret';
GRANT ALL PRIVILEGES ON demo.* TO 'sink'@'%';
GRANT SHOW_ROUTINE ON *.* TO 'sink'@'%';

-- Can read the first table only, so a dump fails after it has started.
CREATE USER IF NOT EXISTS 'partial'@'%'
    IDENTIFIED WITH mysql_native_password BY 'partial';
GRANT SELECT ON demo.widgets TO 'partial'@'%';

-- Has no privileges on demo; used for a failed check probe.
CREATE USER IF NOT EXISTS 'nopriv'@'%'
    IDENTIFIED WITH mysql_native_password BY 'nopriv';
GRANT USAGE ON *.* TO 'nopriv'@'%';

FLUSH PRIVILEGES;
