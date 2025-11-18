CREATE DATABASE bvqz6jhdp0qfrk6tvjtp;

-- Use the database
USE bvqz6jhdp0qfrk6tvjtp;

-- Create Users Table
-- Modified tables with a proper relationship
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fname VARCHAR(255) NOT NULL,
    lname VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE expenses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    food INT NOT NULL,
    travel INT NOT NULL,
    entertainment INT NOT NULL,
    shopping INT NOT NULL,
    other INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);



SHOW TABLE STATUS FROM bvqz6jhdp0qfrk6tvjtp;

drop table expenses;
select * from users;
select * from expenses;