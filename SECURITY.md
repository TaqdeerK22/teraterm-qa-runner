# Security notes

- **No credentials are stored.** Use a `send_secret` step: the password is typed into a masked
  box, substituted into the command in memory and never written to the macro, the pending file
  or the workbook. Do not put passwords in a plain `send` step or in the suite file.
- Results (comments, tester names) are stored in plain text in the workbook and, briefly, in the
  pending file in your results folder. Do not type secrets into comments.
- The tool runs no network code and has no dependencies.

To report a vulnerability, please use GitHub's **Report a vulnerability** (Security tab) rather
than a public issue.
