<?php
$servername = "localhost";
$username = "root";
$password = "";
$database = "login_db";

// Connect to DB
$conn = new mysqli($servername, $username, $password, $database);

if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

// Read data from POST
$name = $_POST['name'];
$email = $_POST['email'];
$role = $_POST['role'];

// Insert into table
$sql = "INSERT INTO users (name, email, role) VALUES ('$name', '$email', '$role')";
if ($conn->query($sql) === TRUE) {
    echo "success";
} else {
    echo "error";
}

$conn->close();
?>
