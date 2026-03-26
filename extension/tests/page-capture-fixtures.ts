export interface HtmlCaptureFixture {
  name: string;
  url: string;
  title: string;
  html: string;
  expected:
    | {
        ok: true;
      }
    | {
        ok: false;
        failureCode: "challenge_page_detected" | "login_required" | "article_body_missing";
      };
}

export interface XmlCaptureFixture {
  name: string;
  responses: Array<{
    url: string;
    ok: boolean;
    text?: string;
    status?: number;
  }>;
  expected:
    | {
        ok: true;
        sourceUrl: string;
      }
    | {
        ok: false;
      };
}

export const HTML_CAPTURE_FIXTURES: HtmlCaptureFixture[] = [
  {
    name: "challenge shell",
    url: "https://example.org",
    title: "Just a moment...",
    html: "<html><body>Just a moment...</body></html>",
    expected: {
      ok: false,
      failureCode: "challenge_page_detected"
    }
  },
  {
    name: "cloudflare managed challenge shell",
    url: "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490",
    title: "Access page",
    html: `
      <html>
        <head><script>window._cf_chl_opt = { cType: 'managed' };</script></head>
        <body>
          <div class="main-wrapper">Enable JavaScript and cookies to continue</div>
          <script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>
          <a href="/doi/full/10.1002/er.7490?__cf_chl_tk=demo">Continue</a>
        </body>
      </html>
    `,
    expected: {
      ok: false,
      failureCode: "challenge_page_detected"
    }
  },
  {
    name: "wiley institutional login shell",
    url: "https://onlinelibrary.wiley.com/doi/10.1002/er.7490",
    title: "Sign in",
    html: "<html><body><form><input type='password'></form><div>Institutional Access</div><div>OpenAthens</div></body></html>",
    expected: {
      ok: false,
      failureCode: "login_required"
    }
  },
  {
    name: "springer institution access shell",
    url: "https://link.springer.com/article/10.1007/demo",
    title: "Access through your institution",
    html: `
      <html>
        <body>
          <div>Access through your institution</div>
          <button>Login via your institution</button>
        </body>
      </html>
    `,
    expected: {
      ok: false,
      failureCode: "login_required"
    }
  },
  {
    name: "springer fulltext page",
    url: "https://link.springer.com/article/10.1000/demo",
    title: "Demo Article",
    html: "<html><head><meta name='citation_doi' content='10.1000/demo'></head><body><main><article><h1>Demo</h1></article></main></body></html>",
    expected: {
      ok: true
    }
  },
  {
    name: "arxiv abstract page",
    url: "https://arxiv.org/abs/2401.00001",
    title: "arXiv Demo",
    html: `
      <html>
        <head>
          <meta name="citation_title" content="Demo arXiv Paper" />
          <meta name="dc:title" content="Demo arXiv Paper" />
          <meta name="dc:identifier" content="arXiv:2401.00001" />
        </head>
        <body>
          <main>
            <section class="abstract">Abstract text</section>
            <section>References</section>
          </main>
        </body>
      </html>
    `,
    expected: {
      ok: true
    }
  },
  {
    name: "arxiv ltx html page with colon metadata",
    url: "https://arxiv.org/html/2401.00001",
    title: "arXiv HTML Demo",
    html: `
      <html>
        <head>
          <meta name="dc:title" content="Demo arXiv HTML Paper" />
          <meta name="dc:identifier" content="10.48550/arXiv.2401.00001" />
        </head>
        <body>
          <article class="ltx_document">
            <section class="ltx_abstract">Abstract text</section>
          </article>
        </body>
      </html>
    `,
    expected: {
      ok: true
    }
  },
  {
    name: "taylor and francis fulltext page",
    url: "https://www.tandfonline.com/doi/full/10.1080/demo",
    title: "Demo T&F Article",
    html: `
      <html>
        <head>
          <meta name="citation_title" content="Demo T&F Article" />
          <meta name="citation_doi" content="10.1080/demo" />
        </head>
        <body>
          <div class="hlFld-Fulltext">
            <div class="abstract">Abstract text</div>
            <div class="references-list">References</div>
          </div>
        </body>
      </html>
    `,
    expected: {
      ok: true
    }
  },
  {
    name: "taylor and francis institutional shell",
    url: "https://www.tandfonline.com/doi/full/10.1080/demo",
    title: "Access through your institution",
    html: `
      <html>
        <body>
          <div>Access through your institution</div>
          <a href="/action/ssostart">Sign in via your institution</a>
          <div>Purchase a subscription to gain access</div>
        </body>
      </html>
    `,
    expected: {
      ok: false,
      failureCode: "login_required"
    }
  },
  {
    name: "wiley pdf iframe shell",
    url: "https://onlinelibrary.wiley.com/doi/pdf/10.1002/er.7490",
    title: "Demo Wiley Shell",
    html: `
      <html>
        <head>
          <meta name="citation_title" content="Demo" />
          <meta name="citation_doi" content="10.1002/er.7490" />
        </head>
        <body>
          <iframe id="pdf-iframe" src="/doi/pdfdirect/10.1002/er.7490" type="application/pdf"></iframe>
        </body>
      </html>
    `,
    expected: {
      ok: false,
      failureCode: "article_body_missing"
    }
  },
  {
    name: "wiley pdf download shell",
    url: "https://onlinelibrary.wiley.com/doi/full/10.1002/demo",
    title: "Demo PDF shell",
    html: `
      <html>
        <head>
          <meta name="citation_title" content="Demo" />
          <meta name="citation_doi" content="10.1002/demo" />
        </head>
        <body>
          <div class="abstract">Short abstract</div>
          <a href="/doi/pdf/10.1002/demo">Download PDF</a>
        </body>
      </html>
    `,
    expected: {
      ok: false,
      failureCode: "article_body_missing"
    }
  },
  {
    name: "springer pdf shell",
    url: "https://link.springer.com/content/pdf/10.1007/demo.pdf",
    title: "Demo Springer PDF shell",
    html: `
      <html>
        <head>
          <meta name="citation_title" content="Demo Springer" />
          <meta name="citation_doi" content="10.1007/demo" />
        </head>
        <body>
          <a href="/content/pdf/10.1007/demo.pdf">Download PDF</a>
        </body>
      </html>
    `,
    expected: {
      ok: false,
      failureCode: "article_body_missing"
    }
  }
];

export const XML_CAPTURE_FIXTURES: XmlCaptureFixture[] = [
  {
    name: "structured article xml after miss",
    responses: [
      {
        url: "https://example.org/miss",
        ok: false,
        status: 404
      },
      {
        url: "https://example.org/paper.xml",
        ok: true,
        text: "<article><body>Demo XML</body></article>"
      }
    ],
    expected: {
      ok: true,
      sourceUrl: "https://example.org/paper.xml"
    }
  },
  {
    name: "skip login shell before xml",
    responses: [
      {
        url: "https://example.org/blocked.xml",
        ok: true,
        text: "<html><body><form><input type='password'></form><div>Institutional Access</div></body></html>"
      },
      {
        url: "https://example.org/paper.xml",
        ok: true,
        text: "<article><body>Demo XML</body></article>"
      }
    ],
    expected: {
      ok: true,
      sourceUrl: "https://example.org/paper.xml"
    }
  },
  {
    name: "skip error envelope before article xml",
    responses: [
      {
        url: "https://example.org/error.xml",
        ok: true,
        text: "<?xml version='1.0'?><error><message>Access denied</message></error>"
      },
      {
        url: "https://example.org/paper.xml",
        ok: true,
        text: "<?xml version='1.0'?><article><body><sec>Demo XML</sec></body></article>"
      }
    ],
    expected: {
      ok: true,
      sourceUrl: "https://example.org/paper.xml"
    }
  }
];
