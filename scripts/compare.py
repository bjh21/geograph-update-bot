import pywikibot
import pywikibot.bot as bot
import pywikibot.comms.http as http
import pywikibot.data.api as api
import subprocess
import tempfile

def url_to_file(url):
    r = http.fetch(url)
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
    return rmse

def compare_by_imageinfo(ii0, ii1):
    return compare_by_url(ii0['thumburl'], ii1['thumburl'],
                          ii0['thumbwidth'], ii0['thumbheight'])

def mark_for_attention(site, title, comment):
    bot.log("marking for human review")
    page = pywikibot.Page(site, title)
    page.text += "\n[[Category:Dubious uploads by Geograph Update Bot]]"
    page.save("Marking last upload for human attention (%s)"
              % (comment,))

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
        try:
            rmse = compare_by_imageinfo(ii[0], ii[1])
        except Exception as e:
            bot.error(str(e))
            mark_for_attention(site, info['title'], str(e))
        else:
            if rmse > 0.09:
                mark_for_attention(site, info['title'], "RMSE = %f" % (rmse,))
