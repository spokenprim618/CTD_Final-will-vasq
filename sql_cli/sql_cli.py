import readline  
import sqlite3   
import sys

conn = sqlite3.connect("../db/100-win-season.db")

cursor = conn.cursor()


tables = cursor.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY 'name'").fetchall()
print("These are the available tables:")
for row in tables:
    print(row[0])
print("Enter your query or exit.")

def main():
    command_buffer = []
    while True:
        try:
            prompt = "sql> " if not command_buffer else "   -> "
            
            line = input(prompt)

            if line.strip().lower() == "exit":
                print("Have a good one.")
                break

            command_buffer.append(line)

            if line.strip().endswith(";"):
                full_command = " ".join(command_buffer).strip()
                command_buffer = []

                try:
                    cursor.execute(full_command)
                    results = cursor.fetchall()
                    for row in results:
                        print(row)
                except sqlite3.Error as e:
                    print(f"SQL Error: {e}")
                
                conn.commit()
                
        except EOFError:  
            print("\nExiting.")
            break
        except KeyboardInterrupt:  
            print("\nCommand canceled.")
            command_buffer = []  

    conn.close()

if __name__ == "__main__":
    main()
