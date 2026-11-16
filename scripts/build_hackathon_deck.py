"""Populate the supplied HackForge OOXML template without changing its masters."""
from pathlib import Path
import zipfile
import xml.etree.ElementTree as E
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SRC = Path.home() / 'Downloads/HackForge_2K26_PPT_Template.pptx'
OUT = ROOT / 'deliverables/CertVault_HackForge_2K26.pptx'
NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
for k,v in NS.items(): E.register_namespace(k,v)
z = zipfile.ZipFile(SRC)
files = {n:z.read(n) for n in z.namelist()}
pres=E.fromstring(files['ppt/presentation.xml']); size=pres.find('p:sldSz',NS)
W,H=int(size.get('cx')),int(size.get('cy'))
def box(tree, ident, x,y,w,h,text,pt=20,bold=False,color='173050'):
    paras=''
    for line in text.split('\n'):
        paras+=f'<a:p><a:pPr><a:spcAft><a:spcPts val="900"/></a:spcAft></a:pPr><a:r><a:rPr lang="en-US" sz="{pt*100}" b="{int(bold)}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Aptos"/></a:rPr><a:t>{escape(line)}</a:t></a:r></a:p>'
    xml=f'<p:sp xmlns:p="{NS["p"]}" xmlns:a="{NS["a"]}"><p:nvSpPr><p:cNvPr id="{ident}" name="CertVault content {ident}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{int(W*x)}" y="{int(H*y)}"/><a:ext cx="{int(W*w)}" cy="{int(H*h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody><a:bodyPr wrap="square" lIns="0" rIns="0" tIns="0" bIns="0"/><a:lstStyle/>{paras}</p:txBody></p:sp>'
    tree.append(E.fromstring(xml))
titles=['CERTVAULT','PROBLEM STATEMENT','SOLUTION & MVP','FLOW OF SOLUTION','TECH STACK','UNIQUE SELLING PROPOSITION','FEASIBILITY & COMPETITORS','RESEARCH & REFERENCES']
contents={
1:[(.07,.32,.85,.12,'Your achievements. One private vault.',32,True),(.07,.48,.85,.08,'Discover certificate PDFs in Gmail and organize proof of learning',22,False),(.07,.63,.85,.26,'Team: Midnight_Hunger  |  Open Innovation – Web\nShourya Rastogi • Vikash Gupta • Shreshtha Pal • Smita Rathi\nKIET Group of Institutions',19,False)],
2:[(.07,.30,.57,.55,'01   Certificates get buried in email\n02   Repeated downloads take manual effort\n03   Filenames hide course and issuer details\n04   Duplicate copies clutter personal folders\n05   Sharing achievements needs privacy controls',23,False),(.69,.32,.25,.43,'WHO IT HELPS\nStudents and lifelong learners\n\nTHE NEED\nOne searchable place for proof of learning',21,True)],
3:[(.06,.29,.43,.59,'THE MVP WORKFLOW\nSign in → Connect Gmail → Scan on demand\n\nDiscover PDF attachments, enforce file limits, scan for malware, extract metadata and save privately.\n\nSearch, view and download certificates. Manual PDF upload provides a second ingestion path.',19,False),(.54,.87,.40,.06,'Actual application screenshot • synthetic demo data',12,False)],
4:[(.07,.28,.86,.60,'01   CONSENT & DISCOVERY\nSupabase Auth → read-only Gmail OAuth → user-triggered scan\n02   CONTROLLED PROCESSING\nFastAPI → Redis / Celery → PDF size checks and approval\n03   SAFE FILE HANDLING\nClamAV → isolated PDF parser → SHA-256 duplicate detection\n04   PRIVATE VAULT\nSupabase Storage + PostgreSQL owner policies → search / view / download',20,False)],
5:[(.07,.30,.27,.40,'FRONTEND\nNext.js + TypeScript\nTailwind CSS + shadcn/ui\nResponsive account and vault UI',20,False),(.37,.30,.27,.40,'BACKEND\nFastAPI + Python\nCelery + Redis\nClamAV + isolated parser',20,False),(.69,.30,.26,.40,'DATA & ACCESS\nSupabase Auth\nPostgreSQL with RLS\nPrivate Storage\nGmail OAuth + Gmail API',20,False),(.07,.77,.85,.13,'LOCAL MVP: Docker Desktop on a laptop; services bound to localhost.\nNo scheduled scans or paid AI service is required for this scope.',18,False)],
6:[(.07,.29,.86,.59,'Certificate-focused discovery instead of generic file collection\nUser-controlled scans with read-only Gmail access\nPrivate storage with ownership enforced on every access\nFile-content duplicate detection using SHA-256\nConfigurable approval threshold within a 50 MB hard cap\n\nFUTURE SCOPE: AI classification, OCR, Microsoft email and selective sharing',22,False)],
7:[(.07,.29,.42,.55,'FEASIBILITY\nLocal stack and test mailbox are configured. Auth and Gmail connection have been exercised.\n\nREMAINING DEMO GATE\nFour scan jobs completed with zero discovered items. Successful real PDF import, storage and delivery still need verification.\n\nLIMITS\nPDF attachments with supported subject wording; no OCR, linked certificates or scheduled scans.',18,False),(.54,.29,.40,.56,'WORKFLOW ALTERNATIVES\n\nEmail inbox\nSearch attachments; organize manually\n\nFile folders\nStore copies; organize filenames manually\n\nCertVault MVP design\nCertificate discovery, extraction, duplicate checks and a private searchable vault\n\nComparison of workflows, not a market ranking',18,False)],
8:[(.07,.29,.50,.58,'PROJECT EVIDENCE\nPRD, architecture, security and test plan in repository\nRecorded checkpoint: 96 Python tests passed\n4 browser journeys passed with mocked APIs\nMocked tests do not prove live Gmail import\n\nTECHNICAL REFERENCES\ndevelopers.google.com/gmail/api\nsupabase.com/docs\ndocs.celeryq.dev',17,False),(.63,.29,.31,.58,'LOCAL DEMO\n127.0.0.1:3000/account\nRuns on the presentation laptop\n\nDEMO SEQUENCE\nSign in → Connect Gmail\nScan → Inspect activity\nOpen vault → View PDF\n\nRepository / video link:\nTo be supplied by the team',18,False)]}
for n in range(1,9):
    path=f'ppt/slides/slide{n}.xml'; root=E.fromstring(files[path]); tree=root.find('p:cSld/p:spTree',NS)
    # Keep template pictures, event branding and footer; replace empty body layouts.
    for el in list(tree):
        if el.tag in (f'{{{NS["p"]}}}sp',f'{{{NS["p"]}}}graphicFrame'):
            tree.remove(el)
    box(tree,100,.055,.055,.60,.06,'HACKFORGE 2K26  |  CODEHIVE',14,True)
    box(tree,101,.07,.14,.86,.13,titles[n-1],36,True)
    box(tree,102,.07,.945,.8,.035,'CERTVAULT  •  HACKATHON MVP  •  NOVEMBER 2026',10,False)
    box(tree,103,.94,.945,.04,.035,str(n),10,False)
    for i,args in enumerate(contents[n]): box(tree,110+i,*args)
    if n==1:
        # Remove template cover texture that otherwise sits behind the new title.
        for el in list(tree):
            if el.tag==f'{{{NS["p"]}}}pic':
                descr=' '.join(el.itertext())
                # Existing pictures and organizer logo stay intact.
    if n==3:
        relpath='ppt/slides/_rels/slide3.xml.rels'; rel=E.fromstring(files[relpath]); R='http://schemas.openxmlformats.org/package/2006/relationships'
        E.SubElement(rel,f'{{{R}}}Relationship',{'Id':'rIdCertVault','Type':NS['r']+'/image','Target':'../media/certvault-dashboard.png'})
        files[relpath]=E.tostring(rel,encoding='utf-8',xml_declaration=True)
        files['ppt/media/certvault-dashboard.png']=(ROOT/'docs/evidence/desktop-overview.png').read_bytes()
        tree.append(E.fromstring(f'<p:pic xmlns:p="{NS["p"]}" xmlns:a="{NS["a"]}" xmlns:r="{NS["r"]}"><p:nvPicPr><p:cNvPr id="190" name="Actual CertVault synthetic demo screenshot"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rIdCertVault"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="{int(W*.56)}" y="{int(H*.28)}"/><a:ext cx="{int(W*.30)}" cy="{int(H*.57)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'))
    files[path]=E.tostring(root,encoding='utf-8',xml_declaration=True)
OUT.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(OUT,'w',zipfile.ZIP_DEFLATED) as target:
    for name,data in files.items(): target.writestr(name,data)
with zipfile.ZipFile(OUT) as check:
    assert check.testzip() is None
    for n in range(1,9): E.fromstring(check.read(f'ppt/slides/slide{n}.xml'))
print(f'Created: {OUT} ({OUT.stat().st_size:,} bytes); 8 slides; OOXML package checks passed')
