from database import get_history_logs

print("\n📊 --- SUPERSHOPPER DATABASE LOG STORAGE --- 📊")
logs = get_history_logs()

if not logs:
    print("The database is currently empty. Run an optimization on the website first!")
else:
    for row in logs:
        print(f"\n[Run #{row[0]}] - Timestamp: {row[1]}")
        print(f"  Target Budget: £{row[2]:.2f}")
        print(f"  Original Total: £{row[3]:.2f}")
        print(f"  Optimized Total: £{row[4]:.2f}")
        print(f"  Budget Triage Applied? {'⚠️ YES' if row[5] == 1 else '✅ NO'}")
print("\n--------------------------------------------")