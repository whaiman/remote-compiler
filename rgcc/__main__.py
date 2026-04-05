"""Entry point for python -m rgcc"""

import sys

if len(sys.argv) > 1 and sys.argv[1] == "server":
    sys.argv.pop(1)
    from rgcc import server_main

    sys.exit(server_main())
else:
    from rgcc import client_main

    sys.exit(client_main())
