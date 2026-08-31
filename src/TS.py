class User:
    users = []

    def add(self, name):
        self.users.append(name)

a = User()
b = User()

a.add("Tom")
print(b.users)