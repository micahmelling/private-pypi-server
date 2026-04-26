# private-pypi-server
Example of how to set up a private pypi server. 

Overall, this effort is functional but could use some work and tightening up. There are a few rough edges, but the most
difficult elements have been figured out. 

To generate the package distribution, you can run the following command.
```bash
$ uv pip install -r requirements.txt
$ python -m build
```

The infrastructure script is run via Pulumi. 

To verify you can install the package...

```bash
$ mkdir pkg-test && cd "$_"
$ uv venv .venv
$ source .venv/bin/activate
$ uv pip install setuptools
$ uv pip install awesomeutils \
  --extra-index-url https://library.mellinganalytics.com/simple/ \
  --index-strategy unsafe-first-match \
  --no-cache
$ python3
$ from awesomeutils.helpers import add_two_numbers
$ add_two_numbers(1, 2)
```

On the uv pip install, the --index-strategy is a bit of a hack to quickly verified the package is installed. 
In production, the flags should be chosen more carefully. Also, in general, it's best for multiple reasons to ensure
your private package has a globally unique name. PyPi is weird about underscores and dashes. For each, I made sure my
package name did not have either. In production, you would want a better naming convention. 

For ongoing updates, in CodeBuild you could:
- generate a new package distribution 
- dynamically update the html files and upload them to s3
- upload the new package distribution to s3
- refresh the cloudfront distribution
