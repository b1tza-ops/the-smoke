from database.bank import BankError, deposit, withdraw

def update_player_balances(player, transaction):

    player.money = transaction.cash_balance
    player.bank_balance = transaction.bank_balance


def deposit_cash(player, amount):

    transaction = deposit(player.id, amount)
    update_player_balances(player, transaction)

    return transaction


def withdraw_cash(player, amount):
    transaction = withdraw(player.id, amount)
    update_player_balances(player, transaction)

    return transaction



def read_amount():
    raw_amount = input("Amount: £").strip()

    try:
        return int(raw_amount)

    except ValueError:
        print("\nEnter a whole number.")
        return None


def bank_menu(player):
    while True:
        print("\n===== BANK =====")
        print(f"Carried cash: £{player.money:,}")
        print(f"Protected funds: £{player.bank_balance:,}")
        print("\n1. Deposit")
        print("2. Withdraw")
        print("3. Back")

        choice = input("Choose: ").strip()

        if choice == "3":
            return

        if choice not in {"1", "2"}:
            print("\nInvalid option.")
            continue

        amount = read_amount()

        if amount is None:
            continue

        try:
            if choice == "1":
                transaction = deposit_cash(player, amount)
                action = "Deposited"
            
            else:
                transaction = withdraw_cash(player,amount)
                action = "Withdrew"

        except BankError as error:
            print(f"\nTransaction failed: {error}")
            continue

        print(f'\n{action} £{transaction.amount:,}')
        print(f"Carried cash: £ {transaction.cash_balance:,}")
        print(f"Protected funds: £{transaction.bank_balance:,}")


