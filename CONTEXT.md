# Personal CUBRID tooling vocabulary

## Language

**pwddb**:
The database alias derived from the current directory's ticket, otherwise the current branch's ticket, otherwise the first ten characters of the current directory name. Hyphens are preserved in the directory fallback.

**Database name suffix**:
An optional label appended to the resolved base name with a hyphen. A suffix identifies a database variant without determining its contents.

**demodb template**:
The sample dataset explicitly selected to populate a database. A database named with the demodb suffix can still be empty unless the template is selected.
