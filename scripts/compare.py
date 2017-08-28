import pywikibot.bot as bot
import pywikibot.data.api as api
import requests
import subprocess
import tempfile

client = requests.Session()

def url_to_file(url):
    r = client.get(url)
    r.raise_for_status()
    tf = tempfile.NamedTemporaryFile()
    tf.write(r.content)
    tf.flush()
    return tf

def compare_by_url(url0, url1, w, h):
    tfs = [url_to_file(url) for url in (url0, url1)]
    inputs = [["JPEG:" + tf.name, '-resize', '%dx%d' % (w, h)] for tf in tfs]
    rmse = float(subprocess.check_output(["convert", "-metric", "rmse"] +
        sum(inputs, []) + ["-compare", "-format", "%[distortion]", "info:"]))
    bot.log("RMSE between newest 2 versions: %f" % rmse)

def compare_revisions(site, parameters):
    # Parameters should include titles= or generator=.
    # This function modifies it.
    parameters.update(dict(prop='imageinfo', iiprop='url', iilimit=2,
                           iiurlwidth=120, iiurlheight=120))
    gen = api.QueryGenerator(site=site, parameters=parameters)
    # HACK
    gen.resultkey='pages'
    for info in gen:
        ii = info['imageinfo']
        if len(ii) < 2: continue
        compare_by_url(ii[0]['thumburl'], ii[1]['thumburl'],
                       ii[0]['thumbwidth'], ii[0]['thumbheight'])

