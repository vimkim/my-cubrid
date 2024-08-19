import gdb

class DumpNodeCommand(gdb.Command):
    """Dump *node to dump.log."""

    def __init__(self):
        super(DumpNodeCommand, self).__init__("dump_node", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        # Execute the gdb command and capture the output
        output = gdb.execute(f"print *{arg}", to_string=True)
        # Print the output to the GDB console
        gdb.write(output)
        # Append the output to dump.log
        with open("dump.log", "a") as f:
            f.write(output)

DumpNodeCommand()

