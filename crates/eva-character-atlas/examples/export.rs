use eva_character_atlas::*;
fn emit(r: Request, first: &mut bool) {
    let f = sample(r).unwrap();
    if !*first {
        println!(",");
    }
    *first = false;
    let colors: Vec<Vec<usize>> = f
        .cells
        .chunks(WIDTH)
        .map(|row| row.iter().map(|c| c.ink as usize).collect())
        .collect();
    println!("{{\"skin\":{:?},\"pose\":{:?},\"mood\":{:?},\"mode\":{:?},\"time_ms\":{},\"seed\":42,\"frame\":{},\"lines\":{:?},\"inks\":{:?},\"palette\":{:?},\"label\":{:?}}}",r.skin.key(),r.pose.key(),r.mood.key(),format!("{:?}",r.motion),r.elapsed_ms,f.frame_index,f.lines(),colors,r.skin.palette(std::env::args().any(|a| a=="--high-contrast")).colors,f.accessible_label);
}
fn main() {
    println!("[");
    let mut first = true;
    if std::env::args().any(|a| a == "--moods") {
        for skin in Skin::ALL {
            for mood in Mood::ALL {
                let mut r = Request::new(skin, Pose::Idle);
                r.motion = Motion::Static;
                r.mood = mood;
                r.seed = 42;
                emit(r, &mut first);
            }
        }
    } else {
        for skin in Skin::ALL {
            for pose in Pose::ALL {
                for motion in [Motion::Full, Motion::Calm, Motion::Static] {
                    let times: Vec<u64> = if motion == Motion::Static {
                        vec![0]
                    } else {
                        let scale = if motion == Motion::Calm { 2 } else { 1 }
                            * if skin == Skin::Night { 2 } else { 1 };
                        let mut sum = 0;
                        pose.durations()
                            .iter()
                            .map(|d| {
                                let t = sum;
                                sum += d * scale;
                                t
                            })
                            .collect()
                    };
                    for time in times {
                        let mut r = Request::new(skin, pose);
                        r.motion = motion;
                        r.elapsed_ms = time;
                        r.seed = 42;
                        emit(r, &mut first);
                    }
                }
            }
        }
    }
    println!("]");
}
