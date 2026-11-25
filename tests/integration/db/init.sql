USE demo;

CREATE USER IF NOT EXISTS 'sink'@'%'
    IDENTIFIED WITH mysql_native_password BY 'p#ass word';
GRANT ALL PRIVILEGES ON demo.* TO 'sink'@'%';
GRANT SHOW_ROUTINE ON *.* TO 'sink'@'%';
FLUSH PRIVILEGES;

CREATE TABLE IF NOT EXISTS widgets (
    id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

INSERT INTO widgets (id, name) VALUES
    (1, 'alpha'),
    (2, 'beta');
