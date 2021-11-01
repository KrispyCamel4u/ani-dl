import sys,getopt,os
from threading import Thread,Lock
import requests,time
lock=Lock()
part_lock=Lock()

is_download=False
output_dir=os.path.dirname(os.path.abspath(__file__))
query=None
num_of_connection=1
num_of_parts_per_download=1
workload=[]
failures=[]

c_red="\033[1;31m"
c_green="\033[1;32m"
c_yellow="\033[1;33m"
c_blue="\033[1;34m"
c_magenta="\033[1;35m"
c_cyan="\033[1;36m"
c_reset="\033[0m"

def usage():
    print("""
    ani_down.py [options] [arguments]
    Options:
    -d : Followed by the name of the anime to download.
    -q : followed by the name of the anime to query.
    """)

try:
    opts, args=getopt.getopt(sys.argv[1:],shortopts="q:hc:o:d:c:p:",longopts=["download=","query=","help","output=","connections="])
except getopt.GetoptError as err:
    print(err)
    usage()
    sys.exit(1)

for opt, arg in opts:
    if opt in ("-d","--download"):
        is_download=True
        query=arg
    elif opt in ("-o","--output"):
        output_dir=os.path.abspath(arg)
    elif opt in ("-c","--connections"):
        num_of_connection=int(arg)
    elif opt in ("-p"):
        num_of_parts_per_download=int(arg)
    elif opt in ("-h", "--help"):
        usage()
        sys.exit()

if output_dir[-1]=="/":
    output_dir = output_dir[:-1]

def get_search_query():
    return input("Search Anime: ")

def search_anime(query):
    query = query.replace(" ","-")
    # print(query)
    command=f"""curl -s https://gogoanime.pe//search.html -G -d keyword={query} | sed -n -E 's_^[[:space:]]*<a href="/category/([^"]*)" title="([^"]*)".*_\\1_p'"""
    p=os.popen(command)
    result=p.read()
    p.close()
    return result.split("\n")[:-1]
    # print(result)

def search_last_ep(anime_id):
    command=f"""curl -s "https://gogoanime.pe/category/{anime_id}\"""" + """|sed -n -E '
		/^[[:space:]]*<a href="#" class="active" ep_start/{
		s/.* '\\''([0-9]*)'\\'' ep_end = '\\''([0-9]*)'\\''.*/\\2/p
		q
		}
		'
    """
    p=os.popen(command)
    lst=int(p.read())
    p.close()
    return lst

def anime_selection(result):
    for count, value in enumerate(result):
        print(f"{c_blue}[{c_cyan}{count}{c_blue}] {c_yellow}{value}{c_reset}")
    choice=None
    while(True):
        choice=int(input(f"{c_blue}Enter number: {c_reset}"))
        if 0<=choice<=len(result):
            if search_last_ep(result[choice])==0:
                print(f"{c_red}No episodes are found for this anime...{c_reset}")
            else:
                break
        else:
            print(f"{c_red}invalid choice.{c_reset}")
    return choice

def episode_selection(result,choice):
    if is_download:
        print("Range of episodes can be specified: start_number end_number")
    inp=input(f"{c_blue}Choose episode [{c_cyan}1-{search_last_ep(result[choice])}{c_blue}]: {c_reset}")
    start_ep=int(inp.split()[0])
    if is_download:
        if len(inp.split())>1:
            end_ep=int(inp.split()[1])
        else:
            end_ep=start_ep
        if start_ep not in range(1,search_last_ep(result[choice])+1) and end_ep not in range(1,search_last_ep(result[choice])+1):
            return episode_selection(result,choice)
        return start_ep, end_ep
    if start_ep not in range(1,search_last_ep(result[choice])+1):
        return episode_selection(result,choice)
    return start_ep

def get_dpage_link(anime_id,episode):
    command=f"""
    curl -s "https://gogoanime.pe/{anime_id}-episode-{episode}" """ + """ |
	sed -n -E '
		/^[[:space:]]*<li class="dowloads">/{
		s/.*href="([^"]*)".*/\\1/p
		q
		}'
    """
    p=os.popen(command)
    dpage_link=p.read()
    p.close()

    return dpage_link

def get_video_link(dpage_url):
    command=f"""
    curl -s "{dpage_url}" """ + """|
	sed -n -E '
		/href="([^"]*)" download>Download/{
		s/href="([^"]*)" download>Download/\\1/p
		q
		}' | tr -d ' '
    """
    p=os.popen(command)
    vid_url=p.read()
    p.close()

    if "streamtape" in vid_url:
        print("scrapping streamtape...")
        command=f"""
        curl -s "{vid_url}" """ + """| sed -n -E '
            /^<script>document/{
            s/^[^"]*"([^"]*)" \\+ '\\''([^'\\'']*).*/https:\\1\\2\\&dl=1/p
            q
            }
        '
        """

    return vid_url

# def get_link_info(result,choice,episode):
#     print(f"{c_green}Getting data for episode {episode} {c_reset}")
#     dpage_url=get_dpage_link(result[choice],episode)
#     if dpage_url[-1]=="\n":
#         dpage_url=dpage_url[:-1]
#     video_url=get_video_link(dpage_url)
#     if video_url[-1]=="\n":
#         video_url=video_url[:-1]

#     # print(f"{c_yellow}dpage_url:{dpage_url}{c_reset}")
#     # print(f"{c_yellow}video_url:{video_url}{c_reset}")

#     print(f"{c_green}Donwloading episode {episode}{c_reset}")
#     header={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:93.0) Gecko/20100101 Firefox/93.0',
#         "Accept-Encoding": "gzip, deflate",
#         "Connection":"keep-alive",
#         }
#     # header["Referer"]=str(dpage_url[:-1])
#     header["Referer"]="https://gogoplay1.com/"
#     return video_url,header

def download_part(video_url,header,work_partition_index,work_partition,episode):
    while(True):
        part_lock.acquire()
        if len(work_partition_index)!=0:
            work_index=work_partition_index.pop(0)
            part_lock.release()
        else:
            part_lock.release()
            break
        h=header.copy()
        h["Range"]=f"bytes={work_partition[work_index][0]}-{work_partition[work_index][1]}"
        response=requests.get(url=video_url,headers=h,stream=True)

        # print(work_partition[work_index][0],work_partition[work_index][1])
        # print(response.headers)
        with open(f"/tmp/{episode}-part-{work_index}","wb") as ifile:
            for chunk in response.iter_content(chunk_size=1024*1024):
                if chunk:
                    ifile.write(chunk)
        response.close()

def download(result,choice):
    while(True):
        lock.acquire()
        if len(workload)!=0:
            episode=workload.pop(0)
            lock.release()
        else:
            lock.release()
            break

        ## Neccessory links
        print(f"{c_green}Getting data for episode {episode} {c_reset}")
        dpage_url=get_dpage_link(result[choice],episode)
        if not dpage_url:
            print(f"{c_red}Empty dpage_url for episode{episode}, trying in 30s...{c_reset}")
            time.sleep(30)
            dpage_url=get_dpage_link(result[choice],episode)
            if not dpage_url:
                print(f"{c_red}Failed to get episode{episode}{c_reset}")
                failures.append(episode)
                continue
        if dpage_url.endswith("\n"):
            dpage_url=dpage_url[:-1]
        video_url=get_video_link(dpage_url)
        if not video_url:
            print(f"{c_red}Empty video_url for episode{episode}, trying in 30s...{c_reset}")
            time.sleep(30)
            video_url=get_video_link(dpage_url)
            if not video_url:
                print(f"{c_red}Failed to get episode{episode}{c_reset}")
                failures.append(episode)
                continue
        if video_url.endswith("\n"):
            video_url = video_url[:-1]

        ## Donwloading area
        header={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:93.0) Gecko/20100101 Firefox/93.0',
            "Accept-Encoding": "gzip, deflate",
            "Connection":"keep-alive",
            "Referer":"https://gogoplay1.com/",
            }
        print(f"{c_green}Donwloading episode {episode}{c_reset}")
        response=requests.get(url=video_url,headers=header,stream=True)
        if not response.ok:
            print(f"{c_red}Error downloading for episode{episode}, trying in 30s...{c_reset}")
            # time.sleep(30)
            response=requests.get(url=video_url,headers=header,stream=True)
            if not response.ok:
                print(f"{c_red}couldn't download episode {episode}{c_reset}")
                failures.append(episode)
                continue

        if "content-length" not in response.headers:
            print(f"{c_cyan}Content Lenght not in header for episode {episode},trying again in 30s...{c_reset}")
            print(response.headers)
            response.close()
            # time.sleep(30)
            response=requests.get(url=video_url,headers=header,stream=True)
            if not response.ok:
                print(f"{c_red}couldn't download episode {episode},{c_reset}")
                failures.append(episode)
                continue
            if "content-length" not in response.headers:
                print(f"{c_red}couldn't download episode {episode},{c_reset}")
                failures.append(episode)
                response.close()
                continue

            # with open(f"{output_dir}/{result[choice]}-{episode}.mp4","wb+") as ifile:
            #     for chunk in response.iter_content(chunk_size=1024*1024):
            #         if chunk:
            #             ifile.write(chunk)
            # response.close()
            # ## Sanity check if the download is successful
            # if os.path.getsize(f"{output_dir}/{result[choice]}-{episode}.mp4")>1024*1024*10:
            #     print(f"{c_magenta}Donwloaded episode {episode}{c_reset}")
            #     os.remove(f"{output_dir}/{result[choice]}-{episode}.mp4")
            # else:
            #     print(f"{c_red}couldn't download episode {episode}{c_reset}")
            #     failures.append(episode)
            # continue
            # print(f"{c_red}couldn't download episode {episode},{c_reset}")
                # failures.append(episode)
                # continue


        file_length=int(response.headers["content-length"])
        response.close()

        ## Download part thread specifics
        work_partition={}
        work_partition_index=[]
        k=0
        # partition_size=3*1024*1024
        partition_size=int(file_length/num_of_parts_per_download)
        for i in range(0,file_length,partition_size): # traverse in lenght of 10MBs=10*1024*1024
            if i+partition_size-1>file_length:
                work_partition[k]=[i,file_length]
            else:
                work_partition[k]=[i,i+partition_size-1]
            work_partition_index.append(k)
            k+=1

        part_threads=[]
        for i in range(num_of_parts_per_download):
            t=Thread(target=download_part,args=(video_url,header,work_partition_index,work_partition,episode))
            part_threads.append(t)
            t.start()
        for i in part_threads:
            i.join()

        with open(f"{output_dir}/{result[choice]}-{episode}.mp4","ab+") as ifile:
            for i in range(k):
                with open(f"/tmp/{episode}-part-{i}","rb") as tfile:
                    ifile.write(tfile.read())
                os.remove(f"/tmp/{episode}-part-{i}")
        ## Last sanity check
        if os.path.getsize(f"{output_dir}/{result[choice]}-{episode}.mp4")==file_length:
            print(f"{c_magenta}Donwloaded episode {episode}{c_reset}")
        else:
            print(f"{c_red}couldn't download episode {episode}{c_reset}")
            os.remove(f"{output_dir}/{result[choice]}-{episode}.mp4")
            failures.append(episode)
        continue
        # print(response.status_code,response.headers)


if __name__ == "__main__":
    if not query:
        query=get_search_query()
    result=search_anime(query)
    while(len(result)==0):
        query=get_search_query()
        result=search_anime(query)
    choice=anime_selection(result)
    # print(choice)
    if is_download:
        start,end=episode_selection(result,choice)
        workload=[i for i in range(start,end+1)]
        threads=[]
        for i in range(num_of_connection):
            t=Thread(target=download,args=(result,choice),)
            t.start()
            threads.append(t)
        for i in threads:
            i.join()

    else:
        print("only downloading works for now")
    if len(failures)!=0:
        print(f"{c_red}list of the episodes that couldn't be downloaded {failures}{c_reset}")
        print(f"{c_yellow}Trying to download these again{c_reset}")
        workload=failures.copy()
        for i in failures:
            download(result,choice)


