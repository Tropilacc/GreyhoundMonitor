from database import connect_database
from database import create_tables


print("===========================")
print(" Greyhound Price Monitor")
print("===========================")

database = connect_database()

create_tables(database)

database.close()

print("Database closed.")