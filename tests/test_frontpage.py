# -*- coding: utf-8 -*-
from skoleintra import pgFrontpage, sbs4

# Opslag fra forsiden som ForældreIntra leverer det bag Cloudflare Rocket
# Loader. Nøglen i data-cf-modified-<nøgle>- er ny ved hver sidevisning
ITEM = u'''<html><body>
<div class="sk-news-item" data-feed-item-type="skoleintra-pin"
     data-feed-item-id="4178">
 <div class="sk-news-item-body">
  <div class="h-dsp-tc sk-news-item-header">
   <div class="sk-news-item-author">
    <span>Clara Jatto Neumann</span>
    <span class="sk-news-item-for"> til </span>
    <span>1A, 1B</span>
   </div>
   <div class="sk-news-item-timestamp h-ws-nowrap">
    30. okt. 2026 11:49 &nbsp;&nbsp;
   </div>
  </div>
  <div class="sk-news-item-content-block">
   <div class="sk-news-item-content">
    <div class="sk-user-input">
     <b>Nyt i fotoalbummet</b><br />Klik p&#229; ikonet herunder for at se
     en billedserie med titlen: <br /><i>Halloween</i>
    </div>
    <div class="sk-news-item-footer">
     <div class="ccl-imagewithtext h-cursor-pointer" data-gallery-id="337"
          tabindex="0" onkeyup="if (!window.__cfRLUnblockHandlers) return
          false; if (event.keyCode === 13) $(this).trigger(&#39;click&#39;);"
          data-cf-modified-%s-="">
      <div class="ccl-imagewithtext-title h-fnt-bd">Halloween</div>
     </div>
    </div>
   </div>
  </div>
 </div>
</div>
<script type="%s-text/javascript" data-cf-settings="%s-|49">x()</script>
</body></html>'''


def page(key):
    return sbs4.beautify(ITEM % (key, key, key))


def test_rocket_loader_noegle_paavirker_ikke_md5():
    a, = pgFrontpage.parseFrontpage(u'Bianca 4B',
                                    page('19e4498be491e6b2ddfea1b6'))
    b, = pgFrontpage.parseFrontpage(u'Bianca 4B',
                                    page('73c6f8ac1703425bc61fd4c5'))
    assert a.getMessageID() == b.getMessageID()
    assert 'data-cf-' not in a.mp['html']
    assert '__cfRL' not in a.mp['html']


def test_rocket_loader_rester_fjernes():
    bs = page('19e4498be491e6b2ddfea1b6')
    div = bs.find('div', 'ccl-imagewithtext')
    assert not [a for a in div.attrs if a.startswith('data-cf-')]
    assert div['onkeyup'].startswith('if (event.keyCode === 13)')
    script = bs.find('script')
    assert script['type'] == 'text/javascript'
    assert not script.has_attr('data-cf-settings')
